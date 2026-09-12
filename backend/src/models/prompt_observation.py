from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class PromptCallObservationModel(Base):
    """Safe per-call LLM diagnostics; prompt/output bodies are never stored."""

    __tablename__ = "prompt_call_observations"
    __table_args__ = (
        Index("ix_prompt_observations_task_created", "task_id", "created_at"),
        Index("ix_prompt_observations_prompt_created", "prompt_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    step_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prompt_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    temperature: Mapped[float | None] = mapped_column(nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    native_json_schema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    repair_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
