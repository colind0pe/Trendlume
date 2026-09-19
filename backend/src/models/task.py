from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.domain.enums import ProductionMode

if TYPE_CHECKING:
    from src.models.product import ProductModel
    from src.models.project import ProjectModel
    from src.models.scene import SceneModel


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("products.id", ondelete="RESTRICT"), nullable=True
    )
    creative_plan_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("commerce_creative_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), default="新视频生成任务", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), default="video_composition", nullable=False)
    production_mode: Mapped[str] = mapped_column(
        String(20), default=ProductionMode.KNOWLEDGE.value, nullable=False
    )
    creative_angle: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="tasks")
    product: Mapped[ProductModel | None] = relationship("ProductModel", lazy="joined")
    scenes: Mapped[list[SceneModel]] = relationship(
        "SceneModel",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="SceneModel.sequence_index",
        lazy="selectin",
    )
