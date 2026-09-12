from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SceneCreate(BaseModel):
    sequence_index: int = Field(default=0, ge=0)
    narration_text: str = ""
    visual_prompt: str = ""
    duration_seconds: float = 4.0
    layout_params: dict[str, Any] = Field(default_factory=dict)
    audio_asset_id: str | None = None
    media_asset_id: str | None = None


class SceneUpdate(BaseModel):
    sequence_index: int | None = None
    narration_text: str | None = None
    visual_prompt: str | None = None
    duration_seconds: float | None = None
    layout_params: dict[str, Any] | None = None
    audio_asset_id: str | None = None
    media_asset_id: str | None = None


class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    sequence_index: int
    narration_text: str
    visual_prompt: str
    duration_seconds: float
    layout_params: dict[str, Any]
    audio_asset_id: str | None = None
    media_asset_id: str | None = None
    rendered_segment_asset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SceneBatchUpdate(BaseModel):
    scenes: list[SceneCreate]
