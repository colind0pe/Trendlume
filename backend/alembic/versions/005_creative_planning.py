"""Add Commerce creative planning and selected-plan task ownership."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005_creative_planning"
down_revision: str | None = "004_commerce_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "commerce_creative_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("source_plan_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("variant_label", sa.String(length=100), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column("angle", sa.String(length=30), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("core_message", sa.Text(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("scene_outline", sa.JSON(), nullable=False),
        sa.Column("cta", sa.Text(), nullable=False),
        sa.Column("truth_sheet_version", sa.Integer(), nullable=False),
        sa.Column("fact_snapshot", sa.JSON(), nullable=False),
        sa.Column("selected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_plan_id"],
            ["commerce_creative_plans.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commerce_creative_plans_product_status",
        "commerce_creative_plans",
        ["product_id", "status"],
        unique=False,
    )
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("creative_plan_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_creative_plan_id",
            "commerce_creative_plans",
            ["creative_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_tasks_creative_plan_id", "tasks", ["creative_plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_creative_plan_id", table_name="tasks")
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_tasks_creative_plan_id", type_="foreignkey")
        batch_op.drop_column("creative_plan_id")
    op.drop_index(
        "ix_commerce_creative_plans_product_status",
        table_name="commerce_creative_plans",
    )
    op.drop_table("commerce_creative_plans")
