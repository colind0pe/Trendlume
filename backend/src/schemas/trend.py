from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.content_modes import LEGACY_CONTENT_MODE, ContentMode
from src.schemas.generation import ContentBrief

TrendSourceStatus = Literal["fresh", "stale", "failed", "unavailable"]
TrendRelation = Literal["high", "medium", "low", "unknown"]
TrendFeedStatus = Literal["ready", "stale", "unavailable"]
TrendFrequency = Literal["15m", "1h", "6h", "24h"]
TrendSubscriptionStatus = Literal["active", "paused", "running", "stale", "failed", "unavailable"]


def _validate_generation_options(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    mode = value.get("content_mode")
    if mode is not None and mode != LEGACY_CONTENT_MODE:
        try:
            ContentMode(mode)
        except ValueError as exc:
            raise ValueError(f"不支持的内容模式：{mode}。") from exc
    return value


class TrendRefreshRequest(BaseModel):
    platforms: list[str] = Field(default_factory=list, max_length=30)
    source_keys: list[str] = Field(default_factory=list, max_length=50)


class TrendSourceRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_key: str
    adapter_name: str
    platform: str
    status: TrendSourceStatus
    item_count: int
    fetched_at: datetime | None = None
    source_updated_at: datetime | None = None
    error_message: str | None = None


class TrendSourceCatalogResponse(BaseModel):
    source_key: str
    adapter_name: str
    platform: str
    platform_label: str
    primary_available: bool = Field(description="是否已配置主源地址；不代表最近一次请求成功。")
    fallback_available: bool = Field(description="是否已配置备用源地址；不代表最近一次请求成功。")


class TrendRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    requested_platforms: list[str]
    source_count: int
    success_count: int
    stale_count: int
    error_count: int
    error_summary: str | None = None
    fetched_at: datetime | None = None
    started_at: datetime
    completed_at: datetime | None = None
    subscription_id: str | None = None
    trigger_key: str | None = None
    sources: list[TrendSourceRunResponse] = Field(default_factory=list)


class TrendItemResponse(BaseModel):
    id: str
    title: str
    platform: str
    platform_label: str | None = None
    rank: int
    raw_metric: str | None = None
    metric_unit: str | None = None
    fetched_at: datetime | None = None
    source_url: str | None = None
    project_relevance: TrendRelation = "unknown"
    source_status: Literal["fresh", "stale", "unavailable"] = "fresh"
    risk_note: str | None = None
    summary: str | None = None


class TrendFeedResponse(BaseModel):
    status: TrendFeedStatus
    items: list[TrendItemResponse] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source_message: str | None = None


class TrendPreferencesUpdate(BaseModel):
    include_keywords: list[str] | None = Field(default=None, max_length=100)
    exclude_keywords: list[str] | None = Field(default=None, max_length=100)
    platforms: list[str] | None = Field(default=None, max_length=30)


class TrendPreferencesResponse(BaseModel):
    project_id: str
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class TrendSubscriptionCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    enabled: bool = True
    platforms: list[str] = Field(default_factory=list, max_length=30)
    source_keys: list[str] = Field(default_factory=list, max_length=50)
    frequency: TrendFrequency = "1h"
    timezone: str = Field(default="UTC", min_length=1, max_length=64)


class TrendSubscriptionUpdate(BaseModel):
    enabled: bool | None = None
    platforms: list[str] | None = Field(default=None, max_length=30)
    source_keys: list[str] | None = Field(default=None, max_length=50)
    frequency: TrendFrequency | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class TrendSourceHealth(BaseModel):
    source_key: str
    platform: str
    status: TrendSourceStatus
    item_count: int
    fetched_at: datetime | None = None
    error_message: str | None = None


class TrendSubscriptionResponse(BaseModel):
    id: str
    project_id: str
    enabled: bool
    platforms: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    frequency: TrendFrequency
    timezone: str
    status: TrendSubscriptionStatus
    retry_count: int
    last_run_id: str | None = None
    last_started_at: datetime | None = None
    last_success_at: datetime | None = None
    next_run_at: datetime | None = None
    last_error: str | None = None
    recent_runs: list[TrendRunResponse] = Field(default_factory=list)
    source_health: list[TrendSourceHealth] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


ProposalStatus = Literal["draft", "approving", "task_created", "queue_failed", "rejected"]


class TrendProposalCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    trend_item_id: str = Field(min_length=1, max_length=36)
    angle: str | None = Field(default=None, max_length=500)
    content_brief: ContentBrief | None = None
    generation_options: dict[str, Any] = Field(default_factory=dict)

    _validate_generation_options = field_validator("generation_options")(
        _validate_generation_options
    )


class TrendProposalUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    angle: str | None = Field(default=None, min_length=1, max_length=500)
    content_brief: ContentBrief | None = None
    generation_options: dict[str, Any] | None = None

    _validate_generation_options = field_validator("generation_options")(
        _validate_generation_options
    )


class TrendProposalApproveRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class TrendProposalRejectRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class TrendProposalResponse(BaseModel):
    id: str
    project_id: str
    trend_item_id: str
    trend_run_id: str | None = None
    trend_observation_id: str | None = None
    task_id: str | None = None
    revision: int
    status: ProposalStatus
    title: str
    angle: str
    match_reason: str
    matched_keywords: list[str] = Field(default_factory=list)
    trend_snapshot: dict[str, Any] = Field(default_factory=dict)
    content_brief: ContentBrief
    generation_options: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TrendProposalActionResponse(BaseModel):
    proposal: TrendProposalResponse
    task: Any | None = None
    job: Any | None = None
    queue_status: Literal["not_requested", "queued", "failed"] = "not_requested"
    queue_error: str | None = None
