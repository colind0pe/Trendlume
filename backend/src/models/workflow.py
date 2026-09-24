from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class WorkflowJobModel(Base):
    """Durable queue record for generation and publishing work."""

    __tablename__ = "workflow_jobs"
    __table_args__ = (
        Index("ix_workflow_jobs_claim", "status", "available_at"),
        Index("ix_workflow_jobs_task", "task_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    production_context_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("production_context_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    current_stage: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class JobEventModel(Base):
    """Append-only event history used to replay SSE events after reconnect."""

    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_id", "job_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_jobs.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class WorkflowStepRunModel(Base):
    __tablename__ = "workflow_step_runs"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "step_key", "unit_key", "attempt", name="uq_workflow_step_attempt"
        ),
        Index("ix_workflow_step_lookup", "task_id", "step_key", "unit_key", "input_fingerprint"),
        Index("ix_workflow_step_job", "job_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    job_id: Mapped[str] = mapped_column(ForeignKey("workflow_jobs.id", ondelete="CASCADE"))
    step_key: Mapped[str] = mapped_column(String(32))
    unit_key: Mapped[str] = mapped_column(String(80), default="")
    attempt: Mapped[int] = mapped_column(Integer)
    implementation_version: Mapped[str] = mapped_column(String(32), default="1")
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    validity: Mapped[str] = mapped_column(String(20), default="valid")
    invalid_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reused_from_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_step_runs.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkflowArtifactModel(Base):
    __tablename__ = "workflow_artifacts"
    __table_args__ = (Index("ix_workflow_artifact_task", "task_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_jobs.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    step_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_step_runs.id", ondelete="CASCADE")
    )
    asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(50))
    relative_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    media_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class WorkflowStepArtifactModel(Base):
    __tablename__ = "workflow_step_artifacts"
    step_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_step_runs.id", ondelete="CASCADE"), primary_key=True
    )
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_artifacts.id", ondelete="NO ACTION"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(12), primary_key=True)
