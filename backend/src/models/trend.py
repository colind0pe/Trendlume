from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class TrendRunModel(Base):
    """One bounded collection attempt across the configured trend sources."""

    __tablename__ = "trend_runs"
    __table_args__ = (
        Index("ix_trend_runs_started", "started_at"),
        UniqueConstraint(
            "subscription_id", "trigger_key", name="uq_trend_runs_subscription_trigger"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    requested_platforms: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stale_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trend_subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    trigger_key: Mapped[str | None] = mapped_column(String(120), nullable=True)


class TrendSourceRunModel(Base):
    """Health and provenance for one source inside a collection run."""

    __tablename__ = "trend_source_runs"
    __table_args__ = (
        UniqueConstraint("run_id", "source_key", name="uq_trend_source_run_key"),
        Index("ix_trend_source_runs_platform_created", "platform", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(100), default="manual", nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="fresh", nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class TrendItemModel(Base):
    """A normalized topic identity shared by observations from different sources."""

    __tablename__ = "trend_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class TrendObservationModel(Base):
    """Platform-specific historical observation; metrics never cross platform boundaries."""

    __tablename__ = "trend_observations"
    __table_args__ = (
        Index("ix_trend_observations_item_fetched", "trend_item_id", "fetched_at"),
        Index("ix_trend_observations_platform_fetched", "platform", "fetched_at"),
        Index("ix_trend_observations_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_source_runs.id", ondelete="CASCADE"), nullable=False
    )
    trend_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_items.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_metric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="fresh", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrendProjectMatchModel(Base):
    """Explainable, run-scoped matching result for a project and normalized topic."""

    __tablename__ = "trend_project_matches"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "project_id",
            "trend_item_id",
            name="uq_trend_project_match_run",
        ),
        Index("ix_trend_project_matches_project_relation", "project_id", "relation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_runs.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    trend_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_items.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, nullable=False)
    matched_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), default="keyword-v1", nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )


class TopicProposalModel(Base):
    """A reviewable topic decision linking one trend snapshot to a project.

    The proposal owns the revision used for approval and keeps the selected
    trend snapshot beside the creative brief. Task creation stores the
    resulting normal Task id here so retries are idempotent without creating a
    second task or a second video workflow.
    """

    __tablename__ = "topic_proposals"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "trend_item_id", name="uq_topic_proposal_project_item"
        ),
        Index("ix_topic_proposals_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    trend_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trend_items.id", ondelete="CASCADE"), nullable=False
    )
    trend_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trend_runs.id", ondelete="SET NULL"), nullable=True
    )
    trend_observation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trend_observations.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    angle: Mapped[str] = mapped_column(String(500), nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    matched_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    trend_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    knowledge_brief: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    generation_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class TrendSubscriptionModel(Base):
    """Project-level trend collection policy and its durable scheduler lease."""

    __tablename__ = "trend_subscriptions"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_trend_subscription_project"),
        Index("ix_trend_subscriptions_due", "enabled", "next_run_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    platforms: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    frequency: Mapped[str] = mapped_column(String(10), default="1h", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
