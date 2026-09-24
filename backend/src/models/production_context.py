from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ProductionContextSnapshotModel(Base):
    """Immutable input boundary for one production execution."""

    __tablename__ = "production_context_snapshots"
    __table_args__ = (
        Index("ix_production_context_snapshots_task_created", "task_id", "created_at"),
        Index("ix_production_context_snapshots_hash", "context_hash"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: f"snapshot_{uuid4().hex[:12]}"
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
