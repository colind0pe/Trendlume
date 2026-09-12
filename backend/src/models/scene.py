from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.task import TaskModel


class SceneModel(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    sequence_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    narration_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    visual_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    layout_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    audio_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    media_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rendered_segment_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    task: Mapped[TaskModel] = relationship("TaskModel", back_populates="scenes")
