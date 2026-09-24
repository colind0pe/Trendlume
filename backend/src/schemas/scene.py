from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.enums import VisualRole
from src.domain.production_recipes import MediaPlan


def _validate_production_metadata(value: dict[str, Any] | None):
    if value and value.get("media_plan") is not None:
        MediaPlan.model_validate(value["media_plan"])
    return value


class SceneCreate(BaseModel):
    sequence_index: int = Field(default=0, ge=0)
    narration_text: str = ""
    visual_prompt: str = ""
    duration_seconds: float = 4.0
    layout_params: dict[str, Any] = Field(default_factory=dict)
    visual_role: VisualRole = VisualRole.CONCEPT
    claim_refs: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    production_metadata: dict[str, Any] = Field(default_factory=dict)
    audio_asset_id: str | None = None
    media_asset_id: str | None = None

    _media_plan = field_validator("production_metadata")(_validate_production_metadata)


class SceneUpdate(BaseModel):
    sequence_index: int | None = None
    narration_text: str | None = None
    visual_prompt: str | None = None
    duration_seconds: float | None = None
    layout_params: dict[str, Any] | None = None
    visual_role: VisualRole | None = None
    claim_refs: list[str] | None = Field(default=None, max_length=20)
    source_refs: list[str] | None = Field(default=None, max_length=20)
    production_metadata: dict[str, Any] | None = None
    audio_asset_id: str | None = None
    media_asset_id: str | None = None

    _media_plan = field_validator("production_metadata")(_validate_production_metadata)


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    sequence_index: int
    narration_text: str
    visual_prompt: str
    duration_seconds: float
    layout_params: dict[str, Any]
    visual_role: str
    claim_refs: list[str]
    source_refs: list[str]
    production_metadata: dict[str, Any]
    audio_asset_id: str | None = None
    media_asset_id: str | None = None
    rendered_segment_asset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SceneBatchUpdate(BaseModel):
    scenes: list[SceneCreate]
