from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import AssetType


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None = None
    asset_type: AssetType
    file_name: str
    file_path: str
    mime_type: str
    file_size_bytes: int
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AssetBatchRequest(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)


class AssetBatchTagsRequest(AssetBatchRequest):
    tags: list[str] = Field(min_length=1, max_length=20)


class AssetBatchSkippedItem(BaseModel):
    id: str
    reason: str


class AssetBatchResult(BaseModel):
    deleted_ids: list[str] = Field(default_factory=list)
    updated_ids: list[str] = Field(default_factory=list)
    skipped: list[AssetBatchSkippedItem] = Field(default_factory=list)
