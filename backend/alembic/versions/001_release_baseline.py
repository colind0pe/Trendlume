"""Initial release schema.

Revision ID: 001_release_baseline
Revises:
Create Date: 2026-09-10 20:41:06.027916

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_release_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("credential_type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cover_asset_id", sa.String(length=36), nullable=True),
        sa.Column("default_voice_id", sa.String(length=100), nullable=True),
        sa.Column("bgm_asset_id", sa.String(length=36), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "prompt_call_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("step_run_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_id", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("template_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("failure_category", sa.String(length=50), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("native_json_schema", sa.Boolean(), nullable=False),
        sa.Column("repair_count", sa.Integer(), nullable=False),
        sa.Column("fallback_count", sa.Integer(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
        sa.Column("output_chars", sa.Integer(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_observations_prompt_created",
        "prompt_call_observations",
        ["prompt_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_prompt_observations_task_created",
        "prompt_call_observations",
        ["task_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("last_test_connected", sa.Boolean(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("last_test_latency_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_provider_configs_is_default"), "provider_configs", ["is_default"], unique=False
    )
    op.create_index(
        op.f("ix_provider_configs_provider_type"),
        "provider_configs",
        ["provider_type"],
        unique=False,
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "project_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=10), nullable=False),
        sa.Column("style_preset", sa.String(length=50), nullable=False),
        sa.Column("template_id", sa.String(length=255), nullable=False),
        sa.Column("template_version", sa.String(length=32), nullable=False),
        sa.Column("font_family", sa.String(length=100), nullable=False),
        sa.Column("primary_color", sa.String(length=20), nullable=False),
        sa.Column("background_color", sa.String(length=20), nullable=False),
        sa.Column("layout_type", sa.String(length=50), nullable=False),
        sa.Column("frame_template", sa.String(length=255), nullable=False),
        sa.Column("custom_css", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("account_name", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("credential_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["credential_id"], ["credentials.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_percentage", sa.Integer(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "publishing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("video_asset_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("cover_asset_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("platform_post_id", sa.String(length=100), nullable=True),
        sa.Column("custom_params", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["social_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scenes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("narration_text", sa.Text(), nullable=False),
        sa.Column("visual_prompt", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("layout_params", sa.JSON(), nullable=False),
        sa.Column("audio_asset_id", sa.String(length=36), nullable=True),
        sa.Column("media_asset_id", sa.String(length=36), nullable=True),
        sa.Column("rendered_segment_asset_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_stage", sa.String(length=50), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_jobs_claim", "workflow_jobs", ["status", "available_at"], unique=False
    )
    op.create_index(
        "ix_workflow_jobs_task", "workflow_jobs", ["task_id", "created_at"], unique=False
    )
    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["workflow_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id", "id"], unique=False)
    op.create_table(
        "workflow_step_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("step_key", sa.String(length=32), nullable=False),
        sa.Column("unit_key", sa.String(length=80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("implementation_version", sa.String(length=32), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validity", sa.String(length=20), nullable=False),
        sa.Column("invalid_reason", sa.Text(), nullable=True),
        sa.Column("reused_from_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["workflow_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reused_from_id"],
            ["workflow_step_runs.id"],
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "step_key", "unit_key", "attempt", name="uq_workflow_step_attempt"
        ),
    )
    op.create_index("ix_workflow_step_job", "workflow_step_runs", ["job_id"], unique=False)
    op.create_index(
        "ix_workflow_step_lookup",
        "workflow_step_runs",
        ["task_id", "step_key", "unit_key", "input_fingerprint"],
        unique=False,
    )
    op.create_table(
        "workflow_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("step_run_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_info", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["step_run_id"], ["workflow_step_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_artifact_task", "workflow_artifacts", ["task_id"], unique=False)
    op.create_table(
        "workflow_step_artifacts",
        sa.Column("step_run_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["workflow_artifacts.id"], ondelete="NO ACTION"),
        sa.ForeignKeyConstraint(["step_run_id"], ["workflow_step_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("step_run_id", "artifact_id", "role"),
    )


def downgrade() -> None:
    op.drop_table("workflow_step_artifacts")
    op.drop_index("ix_workflow_artifact_task", table_name="workflow_artifacts")
    op.drop_table("workflow_artifacts")
    op.drop_index("ix_workflow_step_lookup", table_name="workflow_step_runs")
    op.drop_index("ix_workflow_step_job", table_name="workflow_step_runs")
    op.drop_table("workflow_step_runs")
    op.drop_index("ix_job_events_job_id", table_name="job_events")
    op.drop_table("job_events")
    op.drop_index("ix_workflow_jobs_task", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_claim", table_name="workflow_jobs")
    op.drop_table("workflow_jobs")
    op.drop_table("scenes")
    op.drop_table("publishing_jobs")
    op.drop_table("tasks")
    op.drop_table("social_accounts")
    op.drop_table("project_templates")
    op.drop_table("assets")
    op.drop_index(op.f("ix_provider_configs_provider_type"), table_name="provider_configs")
    op.drop_index(op.f("ix_provider_configs_is_default"), table_name="provider_configs")
    op.drop_table("provider_configs")
    op.drop_index("ix_prompt_observations_task_created", table_name="prompt_call_observations")
    op.drop_index("ix_prompt_observations_prompt_created", table_name="prompt_call_observations")
    op.drop_table("prompt_call_observations")
    op.drop_table("projects")
    op.drop_table("credentials")
