from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class KnowledgeProjectProfileModel(Base):
    __tablename__ = "knowledge_project_profiles"
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    positioning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tone: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    evidence_strategy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    visual_system: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_library: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )
    project = relationship("ProjectModel", back_populates="knowledge_profile")


class CommerceProjectProfileModel(Base):
    __tablename__ = "commerce_project_profiles"
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    brand: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    market: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    default_audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    marketing_goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    brand_tone: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    compliance_constraints: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    visual_system: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    default_cta: Mapped[str] = mapped_column(Text, default="", nullable=False)
    platform_defaults: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )
    project = relationship("ProjectModel", back_populates="commerce_profile")


class DramaProjectProfileModel(Base):
    __tablename__ = "drama_project_profiles"
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    series_title: Mapped[str] = mapped_column(String(255), nullable=False)
    logline: Mapped[str] = mapped_column(Text, default="", nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    tone: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    world_setting: Mapped[str] = mapped_column(Text, default="", nullable=False)
    story_source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    series_bible: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    continuity_rules: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )
    project = relationship("ProjectModel", back_populates="drama_profile")


class DramaStyleGuideModel(Base):
    __tablename__ = "drama_style_guides"
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    medium: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    art_direction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    palette: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    lighting: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    materials: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    cinematography: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    composition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    camera_motion: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    character_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    environment_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    negative_constraints: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    reference_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
