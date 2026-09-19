from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.drama import ApprovalStatus, DramaSourceType, DramaStage, DramaWorkflowStatus


class DramaBibleCreate(BaseModel):
    source_type: DramaSourceType
    title: str = Field(default="未命名短剧", min_length=1, max_length=255)
    source_text: str = Field(min_length=1, max_length=100_000)
    logline: str = Field(default="", max_length=4_000)
    genre: str = Field(default="", max_length=100)
    tone: str = Field(default="", max_length=100)
    visual_style: str = Field(default="电影写实摄影", max_length=1_000)
    continuity_rules: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    prop_locks: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class DramaBibleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    logline: str | None = Field(default=None, max_length=4_000)
    genre: str | None = Field(default=None, max_length=100)
    tone: str | None = Field(default=None, max_length=100)
    visual_style: str | None = Field(default=None, max_length=1_000)
    continuity_rules: list[dict[str, Any]] | None = Field(default=None, max_length=100)
    prop_locks: list[dict[str, Any]] | None = Field(default=None, max_length=100)


class DramaPlanRequest(BaseModel):
    regenerate: bool = False


class DramaApprovalRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2_000)


class DramaCharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=10_000)
    appearance_lock: str | None = Field(default=None, max_length=10_000)
    wardrobe: str | None = Field(default=None, max_length=4_000)
    voice_id: str | None = Field(default=None, max_length=120)
    reference_asset_id: str | None = Field(default=None, max_length=36)
    continuity_metadata: dict[str, Any] | None = None


class DramaLocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    visual_description: str | None = Field(default=None, max_length=10_000)
    reference_asset_ids: list[str] | None = Field(default=None, max_length=50)
    continuity_metadata: dict[str, Any] | None = None


class DramaEpisodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    synopsis: str | None = Field(default=None, max_length=10_000)
    script_text: str | None = Field(default=None, max_length=100_000)
    continuity_metadata: dict[str, Any] | None = None


class DramaSceneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=10_000)
    beat: str | None = Field(default=None, max_length=4_000)
    location_id: str | None = Field(default=None, max_length=36)
    script_text: str | None = Field(default=None, max_length=100_000)
    continuity_metadata: dict[str, Any] | None = None


class DramaShotUpdate(BaseModel):
    action: str | None = Field(default=None, max_length=10_000)
    dialogue: str | None = Field(default=None, max_length=10_000)
    character_ids: list[str] | None = Field(default=None, max_length=30)
    location_id: str | None = Field(default=None, max_length=36)
    camera: str | None = Field(default=None, max_length=255)
    framing: str | None = Field(default=None, max_length=120)
    movement: str | None = Field(default=None, max_length=255)
    duration_hint: float | None = Field(default=None, gt=0, le=60)
    visual_prompt: str | None = Field(default=None, max_length=20_000)
    continuity_metadata: dict[str, Any] | None = None


class DramaStageState(BaseModel):
    status: str
    updated_at: datetime | None = None
    message: str | None = None


class DramaCharacterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bible_id: str
    name: str
    description: str
    appearance_lock: str
    wardrobe: str
    voice_id: str | None = None
    reference_asset_id: str | None = None
    prompt_anchor: str
    continuity_metadata: dict[str, Any]
    approval_status: ApprovalStatus
    approval_note: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DramaLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bible_id: str
    name: str
    visual_description: str
    reference_asset_ids: list[str]
    prompt_anchor: str
    continuity_metadata: dict[str, Any]
    approval_status: ApprovalStatus
    approval_note: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DramaDialogueLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shot_id: str
    sequence_index: int
    character_id: str | None = None
    speaker_name: str
    text: str
    delivery: str
    timing_hint: str
    created_at: datetime
    updated_at: datetime


class DramaShotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scene_id: str
    sequence_index: int
    action: str
    dialogue: str
    character_ids: list[str]
    characters: list[str] = Field(default_factory=list)
    location_id: str | None = None
    camera: str
    framing: str
    movement: str
    duration_hint: float
    visual_prompt: str
    prompt_anchor: str
    continuity_metadata: dict[str, Any]
    approval_status: ApprovalStatus
    approval_note: str | None = None
    approved_at: datetime | None = None
    dialogue_lines: list[DramaDialogueLineResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DramaSceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    episode_id: str
    sequence_index: int
    title: str
    summary: str
    beat: str
    location_id: str | None = None
    script_text: str
    continuity_metadata: dict[str, Any]
    approval_status: ApprovalStatus
    approval_note: str | None = None
    approved_at: datetime | None = None
    shots: list[DramaShotResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DramaEpisodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bible_id: str
    episode_number: int
    title: str
    synopsis: str
    script_text: str
    continuity_metadata: dict[str, Any]
    workflow_status: DramaWorkflowStatus
    approval_status: ApprovalStatus
    approval_note: str | None = None
    checkpoint: dict[str, Any]
    approved_at: datetime | None = None
    scenes: list[DramaSceneResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DramaBibleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_type: DramaSourceType
    source_text: str
    title: str
    logline: str
    genre: str
    tone: str
    visual_style: str
    current_stage: DramaStage
    workflow_status: DramaWorkflowStatus
    approval_status: ApprovalStatus
    stage_state: dict[str, DramaStageState]
    checkpoint: dict[str, Any]
    continuity_rules: list[dict[str, Any]]
    prop_locks: list[dict[str, Any]]
    revision: int
    created_at: datetime
    updated_at: datetime


class DramaDetailResponse(DramaBibleResponse):
    characters: list[DramaCharacterResponse] = Field(default_factory=list)
    locations: list[DramaLocationResponse] = Field(default_factory=list)
    episodes: list[DramaEpisodeResponse] = Field(default_factory=list)


class DramaPreflightResponse(BaseModel):
    drama_id: str
    ready: bool
    blocking: bool
    current_stage: DramaStage
    checks: list[dict[str, Any]] = Field(default_factory=list)


class DramaApprovalResponse(BaseModel):
    drama: DramaDetailResponse
    preflight: DramaPreflightResponse


class DramaProductionStartRequest(BaseModel):
    """Explicit settings for the post-approval Drama production task."""

    episode_id: str | None = Field(default=None, max_length=36)
    visual_mode: Literal["image", "video"] = "image"
    template_id: str = Field(default="image_gallery_matted", min_length=1, max_length=120)
    template_params: dict[str, Any] = Field(default_factory=dict)
    voice_id: str | None = Field(default=None, max_length=120)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    bgm_enabled: bool = False
    bgm_asset_id: str | None = Field(default=None, max_length=36)
    bgm_volume: float = Field(default=0.2, ge=0.0, le=0.5)
    image_workflow_id: str | None = Field(default=None, max_length=255)
    video_workflow_id: str | None = Field(default=None, max_length=255)


class DramaProductionRetryRequest(BaseModel):
    stage: Literal["media", "audio", "composition"] = "media"


class DramaProductionFinding(BaseModel):
    key: str
    label: str
    severity: Literal["info", "warning", "blocking"] = "warning"
    passed: bool
    message: str
    shot_id: str | None = None


class DramaShotProductionResponse(BaseModel):
    shot_id: str
    source_shot_id: str
    sequence_index: int
    status: str
    media_status: str
    audio_status: str
    composition_status: str
    media_asset_id: str | None = None
    audio_asset_id: str | None = None
    rendered_segment_asset_id: str | None = None
    duration_seconds: float | None = None
    dialogue_line_count: int = 0
    dialogue_timeline: list[dict[str, Any]] = Field(default_factory=list)
    qa: list[DramaProductionFinding] = Field(default_factory=list)
    error_message: str | None = None


class DramaProductionResponse(BaseModel):
    drama_id: str
    episode_id: str
    task_id: str | None = None
    job_id: str | None = None
    status: str
    progress: int = 0
    current_stage: str | None = None
    shots: list[DramaShotProductionResponse] = Field(default_factory=list)
    qa_before: list[DramaProductionFinding] = Field(default_factory=list)
    qa_after: list[DramaProductionFinding] = Field(default_factory=list)
    final_video_asset_id: str | None = None
    final_video_url: str | None = None
    subtitle_artifact_ids: list[str] = Field(default_factory=list)
    total_duration_seconds: float | None = None
    error_message: str | None = None
