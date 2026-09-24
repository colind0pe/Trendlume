from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class DramaCharacterModel(Base):
    __tablename__ = "drama_characters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appearance_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    wardrobe_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    voice_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approval_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )


class DramaLocationModel(Base):
    __tablename__ = "drama_locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    visual_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)


class DramaPropModel(Base):
    __tablename__ = "drama_props"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
