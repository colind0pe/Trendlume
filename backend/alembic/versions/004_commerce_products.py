"""Add the Commerce product library and task ownership fields."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004_commerce_products"
down_revision: str | None = "003_production_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=20), nullable=False),
        sa.Column("specifications", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("truth_sheet", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_updated_at", "products", ["updated_at"], unique=False)

    op.create_table(
        "product_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("alt_text", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_assets_product_order",
        "product_assets",
        ["product_id", "sort_order"],
        unique=False,
    )

    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("creative_angle", sa.String(length=30), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_product_id",
            "products",
            ["product_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_tasks_product_id", "tasks", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_product_id", table_name="tasks")
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_tasks_product_id", type_="foreignkey")
        batch_op.drop_column("creative_angle")
        batch_op.drop_column("product_id")
    op.drop_index("ix_product_assets_product_order", table_name="product_assets")
    op.drop_table("product_assets")
    op.drop_index("ix_products_updated_at", table_name="products")
    op.drop_table("products")
