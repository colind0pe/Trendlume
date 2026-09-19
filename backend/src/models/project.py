from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.domain.enums import ProductionMode

if TYPE_CHECKING:
    from src.models.asset import AssetModel
    from src.models.drama import DramaBibleModel
    from src.models.task import TaskModel
    from src.models.template import ProjectTemplateModel


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16", nullable=False)
    primary_production_mode: Mapped[str] = mapped_column(
        String(20), default=ProductionMode.KNOWLEDGE.value, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    cover_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    default_voice_id: Mapped[str | None] = mapped_column(
        String(100), default="zh-CN-YunxiNeural", nullable=True
    )
    bgm_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
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
    template: Mapped[ProjectTemplateModel | None] = relationship(
        "ProjectTemplateModel",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tasks: Mapped[list[TaskModel]] = relationship(
        "TaskModel",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="TaskModel.created_at.desc()",
        lazy="selectin",
    )
    assets: Mapped[list[AssetModel]] = relationship(
        "AssetModel",
        back_populates="project",
        lazy="selectin",
    )
    drama_bibles: Mapped[list[DramaBibleModel]] = relationship(
        "DramaBibleModel",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="DramaBibleModel.updated_at.desc()",
        lazy="selectin",
    )
