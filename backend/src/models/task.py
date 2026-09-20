from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class TaskModel(Base):
    """One editable video or episode; execution state belongs to WorkflowJob."""

    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    editorial_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    production_status: Mapped[str] = mapped_column(
        String(30), default="not_started", nullable=False
    )
    generation_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    publishing_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    project = relationship("ProjectModel", back_populates="tasks", lazy="joined")
    knowledge_detail = relationship(
        "KnowledgeTaskDetailModel", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    commerce_detail = relationship(
        "CommerceTaskDetailModel", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    drama_episode = relationship(
        "DramaTaskEpisodeModel", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    scenes = relationship(
        "SceneModel",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="SceneModel.sequence_index",
        lazy="selectin",
    )
