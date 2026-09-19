import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.domain.enums import JobStatus, JobType


@dataclass
class Job:
    id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")
    task_id: str = ""
    job_type: str = JobType.FULL_PIPELINE.value
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    current_stage: str = "queued"
    error_message: str | None = None
    lease_token: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    available_at: datetime | None = None
    scheduled_at: datetime | None = None
    updated_at: datetime | None = None
    checkpoint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "job_type": self.job_type,
            "status": self.status.value if isinstance(self.status, JobStatus) else str(self.status),
            "progress": self.progress,
            "current_stage": self.current_stage,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "heartbeat_at": self.heartbeat_at.isoformat() if self.heartbeat_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "params": self.params,
            "checkpoint": self.checkpoint,
            "result": self.result,
        }
