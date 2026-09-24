from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkflowJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    production_context_snapshot_id: str
    job_type: str
    status: str
    current_stage: str
    progress: int
    params: dict[str, Any]
    checkpoint: dict[str, Any]
    result: dict[str, Any] | None = None
    retry_count: int
    max_retries: int
    available_at: datetime
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    stages: list["WorkflowStepRunResponse"] = Field(default_factory=list)
    artifacts: list["WorkflowArtifactResponse"] = Field(default_factory=list)

    @field_validator(
        "available_at", "scheduled_at", "started_at", "heartbeat_at", "completed_at", "created_at", "updated_at",
        mode="before",
    )
    @classmethod
    def normalize_utc(cls, value: datetime | str | None) -> datetime | str | None:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class TaskResumeRequest(BaseModel):
    job_id: str | None = None


class WorkflowArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: str
    task_id: str
    step_run_id: str
    asset_id: str | None = None
    kind: str
    relative_path: str
    size_bytes: int
    sha256: str
    media_info: dict[str, Any] | None = None
    source: str
    created_at: datetime


class WorkflowStepRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    task_id: str
    job_id: str
    step_key: str
    unit_key: str
    attempt: int
    implementation_version: str
    input_fingerprint: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    status: str
    validity: str
    invalid_reason: str | None = None
    reused_from_id: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    warning: str | None = None
    artifacts: list[WorkflowArtifactResponse] = Field(default_factory=list)


class WorkflowStepRetryRequest(BaseModel):
    unit_key: str | None = None


class WorkflowStageSummaryResponse(BaseModel):
    step_key: str
    label: str = ""
    status: str
    validity: str
    duration_ms: int
    retry_count: int
    units: list[WorkflowStepRunResponse]
    history: list[WorkflowStepRunResponse]


class WorkflowSnapshotResponse(BaseModel):
    task_id: str
    stages: list[WorkflowStageSummaryResponse]
