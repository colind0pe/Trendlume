from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class ProjectAssetBindingModel(Base):
    __tablename__ = "project_asset_bindings"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_id", "purpose", name="uq_project_asset_purpose"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ProjectModel(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("mode IN ('knowledge', 'commerce', 'drama')", name="ck_projects_mode"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(10), default="9:16", nullable=False)
    default_production_settings: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    tasks = relationship(
        "TaskModel", back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    knowledge_profile = relationship(
        "KnowledgeProjectProfileModel",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    commerce_profile = relationship(
        "CommerceProjectProfileModel",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    drama_profile = relationship(
        "DramaProjectProfileModel",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    drama_style_guide = relationship(
        "DramaStyleGuideModel", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )
    asset_bindings = relationship(
        "ProjectAssetBindingModel", cascade="all, delete-orphan", lazy="selectin"
    )
    products = relationship(
        "ProductModel", back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    template = relationship(
        "ProjectTemplateModel",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
