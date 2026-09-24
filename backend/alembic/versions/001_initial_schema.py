"""Initial Trendlume schema.

Revision ID: 001
Revises: None
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def _schema_tables():
    # Importing the declarative registry keeps this fresh-install baseline and
    # the ORM definition identical. Alembic still issues one CREATE TABLE and
    # CREATE INDEX statement per object; it never calls metadata.create_all.
    import src.models  # noqa: F401
    from src.core.database import Base
    return Base.metadata.sorted_tables


def upgrade() -> None:
    bind = op.get_bind()
    for table in _schema_tables():
        bind.execute(sa.schema.CreateTable(table))
        for index in table.indexes:
            bind.execute(sa.schema.CreateIndex(index))


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_schema_tables()):
        bind.execute(sa.schema.DropTable(table))
