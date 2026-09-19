from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.domain.drama import (
    ApprovalStatus,
    DramaStage,
    DramaWorkflowStatus,
)

if TYPE_CHECKING:
    from src.models.asset import AssetModel
    from src.models.project import ProjectModel


def _now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex[:12]}"


class DramaBibleModel(Base):
    """The durable creative source of truth for Drama pre-production."""

    __tablename__ = "drama_bibles"
    __table_args__ = (Index("ix_drama_bibles_project_updated", "project_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("drama"))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    logline: Mapped[str] = mapped_column(Text, default="", nullable=False)
    genre: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    tone: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    visual_style: Mapped[str] = mapped_column(Text, default="", nullable=False)
    current_stage: Mapped[str] = mapped_column(
        String(30), default=DramaStage.STORY.value, nullable=False
    )
    workflow_status: Mapped[str] = mapped_column(
        String(30), default=DramaWorkflowStatus.DRAFT.value, nullable=False
    )
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.DRAFT.value, nullable=False
    )
    stage_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    continuity_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    prop_locks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    project: Mapped[ProjectModel] = relationship(
        "ProjectModel", back_populates="drama_bibles", lazy="joined"
    )
    characters: Mapped[list[DramaCharacterModel]] = relationship(
        "DramaCharacterModel",
        back_populates="bible",
        cascade="all, delete-orphan",
        order_by="DramaCharacterModel.created_at",
        lazy="selectin",
    )
    locations: Mapped[list[DramaLocationModel]] = relationship(
        "DramaLocationModel",
        back_populates="bible",
        cascade="all, delete-orphan",
        order_by="DramaLocationModel.created_at",
        lazy="selectin",
    )
    episodes: Mapped[list[DramaEpisodeModel]] = relationship(
        "DramaEpisodeModel",
        back_populates="bible",
        cascade="all, delete-orphan",
        order_by="DramaEpisodeModel.episode_number",
        lazy="selectin",
    )


class DramaCharacterModel(Base):
    __tablename__ = "drama_characters"
    __table_args__ = (Index("ix_drama_characters_bible_approval", "bible_id", "approval_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("character"))
    bible_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_bibles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appearance_lock: Mapped[str] = mapped_column(Text, default="", nullable=False)
    wardrobe: Mapped[str] = mapped_column(Text, default="", nullable=False)
    voice_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reference_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    prompt_anchor: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    continuity_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.DRAFT.value, nullable=False
    )
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    bible: Mapped[DramaBibleModel] = relationship("DramaBibleModel", back_populates="characters")
    reference_asset: Mapped[AssetModel | None] = relationship(
        "AssetModel", foreign_keys=[reference_asset_id], lazy="joined"
    )


class DramaLocationModel(Base):
    __tablename__ = "drama_locations"
    __table_args__ = (Index("ix_drama_locations_bible_approval", "bible_id", "approval_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("location"))
    bible_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_bibles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    visual_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reference_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    prompt_anchor: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    continuity_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.DRAFT.value, nullable=False
    )
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    bible: Mapped[DramaBibleModel] = relationship("DramaBibleModel", back_populates="locations")


class DramaEpisodeModel(Base):
    __tablename__ = "drama_episodes"
    __table_args__ = (
        UniqueConstraint("bible_id", "episode_number", name="uq_drama_episode_number"),
        Index("ix_drama_episodes_bible_status", "bible_id", "approval_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("episode"))
    bible_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_bibles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    synopsis: Mapped[str] = mapped_column(Text, default="", nullable=False)
    script_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    workflow_status: Mapped[str] = mapped_column(
        String(30), default=DramaWorkflowStatus.DRAFT.value, nullable=False
    )
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.DRAFT.value, nullable=False
    )
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    bible: Mapped[DramaBibleModel] = relationship("DramaBibleModel", back_populates="episodes")
    scenes: Mapped[list[DramaSceneModel]] = relationship(
        "DramaSceneModel",
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="DramaSceneModel.sequence_index",
        lazy="selectin",
    )


class DramaSceneModel(Base):
    __tablename__ = "drama_scenes"
    __table_args__ = (
        UniqueConstraint("episode_id", "sequence_index", name="uq_drama_scene_sequence"),
        Index("ix_drama_scenes_episode_status", "episode_id", "approval_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("scene"))
    episode_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_episodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    beat: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drama_locations.id", ondelete="SET NULL"), nullable=True
    )
    script_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    continuity_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.DRAFT.value, nullable=False
    )
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    episode: Mapped[DramaEpisodeModel] = relationship("DramaEpisodeModel", back_populates="scenes")
    location: Mapped[DramaLocationModel | None] = relationship(
        "DramaLocationModel", foreign_keys=[location_id], lazy="joined"
    )
    shots: Mapped[list[DramaShotModel]] = relationship(
        "DramaShotModel",
        back_populates="scene",
        cascade="all, delete-orphan",
        order_by="DramaShotModel.sequence_index",
        lazy="selectin",
    )


class DramaShotModel(Base):
    __tablename__ = "drama_shots"
    __table_args__ = (
        UniqueConstraint("scene_id", "sequence_index", name="uq_drama_shot_sequence"),
        Index("ix_drama_shots_scene_status", "scene_id", "approval_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("shot"))
    scene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    location_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drama_locations.id", ondelete="SET NULL"), nullable=True
    )
    camera: Mapped[str] = mapped_column(String(255), default="固定机位", nullable=False)
    framing: Mapped[str] = mapped_column(String(120), default="中景", nullable=False)
    movement: Mapped[str] = mapped_column(String(255), default="固定", nullable=False)
    duration_hint: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    visual_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prompt_anchor: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    continuity_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.DRAFT.value, nullable=False
    )
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    scene: Mapped[DramaSceneModel] = relationship("DramaSceneModel", back_populates="shots")
    location: Mapped[DramaLocationModel | None] = relationship(
        "DramaLocationModel", foreign_keys=[location_id], lazy="joined"
    )
    dialogue_lines: Mapped[list[DramaDialogueLineModel]] = relationship(
        "DramaDialogueLineModel",
        back_populates="shot",
        cascade="all, delete-orphan",
        order_by="DramaDialogueLineModel.sequence_index",
        lazy="selectin",
    )

    @property
    def dialogue(self) -> str:
        """Render the normalized dialogue lines for API and review consumers."""
        return "\n".join(
            f"{line.speaker_name}: {line.text}" if line.speaker_name != "旁白" else line.text
            for line in self.dialogue_lines
        )

    @property
    def characters(self) -> list[str]:
        """Return character IDs for the domain/API representation."""

        return list(self.character_ids or [])


class DramaDialogueLineModel(Base):
    __tablename__ = "drama_dialogue_lines"
    __table_args__ = (
        UniqueConstraint("shot_id", "sequence_index", name="uq_drama_dialogue_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: _id("dialogue"))
    shot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drama_shots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    character_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drama_characters.id", ondelete="SET NULL"), nullable=True
    )
    speaker_name: Mapped[str] = mapped_column(String(120), default="旁白", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    delivery: Mapped[str] = mapped_column(String(160), default="自然", nullable=False)
    timing_hint: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    shot: Mapped[DramaShotModel] = relationship("DramaShotModel", back_populates="dialogue_lines")
    character: Mapped[DramaCharacterModel | None] = relationship(
        "DramaCharacterModel", foreign_keys=[character_id], lazy="joined"
    )
