from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class KnowledgeTaskDetailModel(Base):
    __tablename__ = "knowledge_task_details"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    thesis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    takeaway: Mapped[str] = mapped_column(Text, default="", nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="auto", nullable=False)
    claims: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    sources: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    content_structure: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    script: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )


class CommerceTaskDetailModel(Base):
    __tablename__ = "commerce_task_details"

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    creative_angle: Mapped[str] = mapped_column(String(100), nullable=False)
    hook: Mapped[str] = mapped_column(Text, default="", nullable=False)
    audience: Mapped[str] = mapped_column(Text, default="", nullable=False)
    core_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    selected_claims: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    scene_outline: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    cta: Mapped[str] = mapped_column(Text, default="", nullable=False)
    offer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    product_facts_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    script: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )


class DramaTaskEpisodeModel(Base):
    __tablename__ = "drama_task_episodes"
    __table_args__ = (
        UniqueConstraint("project_id", "episode_number", name="uq_drama_task_episode_number"),
    )

    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    script_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    production_checkpoint: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )

    scenes: Mapped[list[DramaTaskSceneModel]] = relationship(
        "DramaTaskSceneModel",
        cascade="all, delete-orphan",
        order_by="DramaTaskSceneModel.sequence_index",
    )


class DramaTaskSceneModel(Base):
    __tablename__ = "drama_task_scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task_episodes.task_id", ondelete="CASCADE"), nullable=False
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drama_locations.id", ondelete="RESTRICT"), nullable=True
    )
    script_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)


class DramaTaskShotModel(Base):
    __tablename__ = "drama_task_shots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task_scenes.id", ondelete="CASCADE"), nullable=False
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drama_locations.id", ondelete="RESTRICT"), nullable=True
    )
    camera: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    framing: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    movement: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    duration_hint: Mapped[float] = mapped_column(default=4.0, nullable=False)
    visual_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)


class DramaTaskDialogueLineModel(Base):
    __tablename__ = "drama_task_dialogue_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    shot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_task_shots.id", ondelete="CASCADE"), nullable=False
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    character_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drama_characters.id", ondelete="RESTRICT"), nullable=True
    )
    speaker_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    delivery: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    timing_hint: Mapped[str] = mapped_column(String(120), default="", nullable=False)
