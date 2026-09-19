"""Align production-domain indexes with the ORM metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_align_production_indexes"
down_revision: str | None = "006_drama_preproduction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Production mode is authoritative on tasks.production_mode. Remove the
    # duplicate JSON value written by the pre-Production-Mode task builder.
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            sa.text(
                "UPDATE tasks "
                "SET input_payload = json_remove(input_payload, '$.production_mode') "
                "WHERE input_payload IS NOT NULL"
            )
        )
    op.drop_index(
        "ix_commerce_creative_plans_product_status",
        table_name="commerce_creative_plans",
    )
    op.create_index(
        "ix_commerce_creative_plans_product_id",
        "commerce_creative_plans",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commerce_creative_plans_product_id",
        table_name="commerce_creative_plans",
    )
    op.create_index(
        "ix_commerce_creative_plans_product_status",
        "commerce_creative_plans",
        ["product_id", "status"],
        unique=False,
    )
