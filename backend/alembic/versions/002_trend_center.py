"""Add the persisted trend collection, proposal, and automation boundary."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_trend_center"
down_revision: str | None = "001_release_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trend_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("platforms", sa.JSON(), nullable=False),
        sa.Column("source_keys", sa.JSON(), nullable=False),
        sa.Column("frequency", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_run_id", sa.String(length=36), nullable=True),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_trend_subscription_project"),
    )
    op.create_index(
        "ix_trend_subscriptions_due",
        "trend_subscriptions",
        ["enabled", "next_run_at"],
        unique=False,
    )

    op.create_table(
        "trend_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_platforms", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("stale_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=True),
        sa.Column("trigger_key", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["trend_subscriptions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscription_id", "trigger_key", name="uq_trend_runs_subscription_trigger"
        ),
    )
    op.create_index("ix_trend_runs_started", "trend_runs", ["started_at"], unique=False)

    op.create_table(
        "trend_source_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("adapter_name", sa.String(length=100), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["trend_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "source_key", name="uq_trend_source_run_key"),
    )
    op.create_index(
        "ix_trend_source_runs_platform_created",
        "trend_source_runs",
        ["platform", "created_at"],
        unique=False,
    )

    op.create_table(
        "trend_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canonical_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_key"),
    )

    op.create_table(
        "trend_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=False),
        sa.Column("trend_item_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("raw_metric", sa.String(length=100), nullable=True),
        sa.Column("metric_unit", sa.String(length=50), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["trend_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["trend_source_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trend_item_id"], ["trend_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trend_observations_item_fetched",
        "trend_observations",
        ["trend_item_id", "fetched_at"],
        unique=False,
    )
    op.create_index(
        "ix_trend_observations_platform_fetched",
        "trend_observations",
        ["platform", "fetched_at"],
        unique=False,
    )
    op.create_index("ix_trend_observations_run", "trend_observations", ["run_id"], unique=False)

    op.create_table(
        "trend_project_matches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("trend_item_id", sa.String(length=36), nullable=False),
        sa.Column("relation", sa.String(length=20), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("matched_keywords", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["trend_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["trend_item_id"], ["trend_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "project_id", "trend_item_id", name="uq_trend_project_match_run"
        ),
    )
    op.create_index(
        "ix_trend_project_matches_project_relation",
        "trend_project_matches",
        ["project_id", "relation"],
        unique=False,
    )

    op.create_table(
        "topic_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("trend_item_id", sa.String(length=36), nullable=False),
        sa.Column("trend_run_id", sa.String(length=36), nullable=True),
        sa.Column("trend_observation_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("angle", sa.String(length=500), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("matched_keywords", sa.JSON(), nullable=False),
        sa.Column("trend_snapshot", sa.JSON(), nullable=False),
        sa.Column("content_brief", sa.JSON(), nullable=False),
        sa.Column("generation_options", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trend_item_id"], ["trend_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trend_run_id"], ["trend_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["trend_observation_id"], ["trend_observations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "trend_item_id", name="uq_topic_proposal_project_item"),
    )
    op.create_index(
        "ix_topic_proposals_project_status",
        "topic_proposals",
        ["project_id", "status"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index("ix_topic_proposals_project_status", table_name="topic_proposals")
    op.drop_table("topic_proposals")
    op.drop_index("ix_trend_project_matches_project_relation", table_name="trend_project_matches")
    op.drop_table("trend_project_matches")
    op.drop_index("ix_trend_observations_run", table_name="trend_observations")
    op.drop_index("ix_trend_observations_platform_fetched", table_name="trend_observations")
    op.drop_index("ix_trend_observations_item_fetched", table_name="trend_observations")
    op.drop_table("trend_observations")
    op.drop_table("trend_items")
    op.drop_index("ix_trend_source_runs_platform_created", table_name="trend_source_runs")
    op.drop_table("trend_source_runs")
    op.drop_index("ix_trend_runs_started", table_name="trend_runs")
    op.drop_table("trend_runs")
    op.drop_index("ix_trend_subscriptions_due", table_name="trend_subscriptions")
    op.drop_table("trend_subscriptions")
