"""Add production mode ownership to projects and tasks."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_production_mode"
down_revision: str | None = "002_trend_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    default = sa.text("'knowledge'")
    op.add_column(
        "projects",
        sa.Column(
            "primary_production_mode",
            sa.String(length=20),
            nullable=False,
            server_default=default,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "production_mode",
            sa.String(length=20),
            nullable=False,
            server_default=default,
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "visual_role",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'concept'"),
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "claim_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "source_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "production_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.execute(sa.text("UPDATE projects SET primary_production_mode = 'knowledge'"))
    op.execute(sa.text("UPDATE tasks SET production_mode = 'knowledge'"))


def downgrade() -> None:
    op.drop_column("scenes", "production_metadata")
    op.drop_column("scenes", "source_refs")
    op.drop_column("scenes", "claim_refs")
    op.drop_column("scenes", "visual_role")
    op.drop_column("tasks", "production_mode")
    op.drop_column("projects", "primary_production_mode")
