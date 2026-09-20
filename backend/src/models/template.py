from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.project import ProjectModel


class ProjectTemplateModel(Base):
    __tablename__ = "project_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), default="默认排版模版", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16", nullable=False)
    style_preset: Mapped[str] = mapped_column(String(50), default="modern_clean", nullable=False)
    template_id: Mapped[str] = mapped_column(
        String(255), default="image_gallery_matted", nullable=False
    )
    template_version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    font_family: Mapped[str] = mapped_column(
        String(100), default="Inter, sans-serif", nullable=False
    )
    primary_color: Mapped[str] = mapped_column(String(20), default="#a855f7", nullable=False)
    background_color: Mapped[str] = mapped_column(String(20), default="#0f172a", nullable=False)
    layout_type: Mapped[str] = mapped_column(String(50), default="split_card", nullable=False)
    frame_template: Mapped[str] = mapped_column(
        String(255), default="1080x1920/default.html", nullable=False
    )
    custom_css: Mapped[str] = mapped_column(Text, default="", nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
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
    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="template")
