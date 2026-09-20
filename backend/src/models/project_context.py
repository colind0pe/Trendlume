from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.project import ProjectModel
    from src.models.task import TaskModel


def _now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex[:12]}"


class ProjectContextVersionModel(Base):
    """Immutable, content-addressed snapshot of a project's creative context."""

    __tablename__ = "project_context_versions"
    __table_args__ = (
        Index("ix_project_context_versions_project_version", "project_id", "version"),
        Index("ix_project_context_versions_hash", "context_hash"),
        UniqueConstraint("project_id", "version", name="uq_project_context_version"),
        UniqueConstraint("project_id", "context_hash", name="uq_project_context_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("ctx"))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    context_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="context_versions")
    tasks: Mapped[list[TaskModel]] = relationship(
        "TaskModel", back_populates="project_context_version"
    )


class KnowledgeProjectProfileModel(Base):
    """Typed Knowledge defaults kept under the Project aggregate."""

    __tablename__ = "knowledge_project_profiles"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    positioning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    default_audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tone: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    visual_system: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_strategy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="knowledge_profile")


class CommerceProjectProfileModel(Base):
    """Typed Commerce defaults kept beside the existing product library."""

    __tablename__ = "commerce_project_profiles"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    brand: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    market: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    marketing_goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    brand_tone: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    visual_system: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    default_cta: Mapped[str] = mapped_column(Text, default="", nullable=False)
    compliance_limits: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    platform_defaults: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="commerce_profile")


class KnowledgeContentItemModel(Base):
    """A typed Knowledge item that can be pinned by a Task."""

    __tablename__ = "knowledge_content_items"
    __table_args__ = (
        Index("ix_knowledge_content_items_project_status", "project_id", "review_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("knowledge"))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    thesis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    takeaway: Mapped[str] = mapped_column(Text, default="", nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="auto", nullable=False)
    key_claims: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    source_refs: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="knowledge_items")
    tasks: Mapped[list[TaskModel]] = relationship("TaskModel", back_populates="knowledge_item")
