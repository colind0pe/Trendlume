from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from src.core.config import settings
from src.core.database import verify_schema
from src.models import Base

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
BASELINE_REVISION = "001_release_baseline"
RELEASE_REVISION = "006_drama_preproduction"


def _migration_database(tmp_path: Path, filename: str) -> tuple[Path, str]:
    database_file = tmp_path / filename
    return database_file, f"sqlite+aiosqlite:///{database_file.as_posix()}"


def _run_migration(database_url: str, revision: str, *, downgrade: bool = False) -> None:
    original_database_url = settings.database_url
    try:
        settings.database_url = database_url
        alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        (command.downgrade if downgrade else command.upgrade)(alembic_config, revision)
    finally:
        settings.database_url = original_database_url


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table_name}")')}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not row[0].startswith("sqlite_")
    }


def _migration_version(connection: sqlite3.Connection) -> str:
    return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_head_creates_current_schema(tmp_path: Path):
    database_file, database_url = _migration_database(tmp_path, "release.db")

    _run_migration(database_url, "head")

    with sqlite3.connect(database_file) as connection:
        assert _table_names(connection) == set(Base.metadata.tables) | {"alembic_version"}
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            RELEASE_REVISION,
        )
        assert "task_batches" not in _table_names(connection)
        assert "batch_id" not in _table_columns(connection, "tasks")
        assert "lease_token" in _table_columns(connection, "workflow_jobs")
        assert {
            "last_test_connected",
            "last_tested_at",
            "last_test_message",
            "last_test_latency_ms",
        } <= _table_columns(connection, "provider_configs")
        assert {
            "content_brief",
            "generation_options",
        } <= _table_columns(connection, "topic_proposals")
        assert "primary_production_mode" in _table_columns(connection, "projects")
        assert "production_mode" in _table_columns(connection, "tasks")
        assert {"product_id", "creative_angle"} <= _table_columns(connection, "tasks")
        assert {"products", "product_assets", "commerce_creative_plans"} <= _table_names(connection)
        assert {
            "drama_bibles",
            "drama_characters",
            "drama_locations",
            "drama_episodes",
            "drama_scenes",
            "drama_shots",
            "drama_dialogue_lines",
        } <= _table_names(connection)
        assert "creative_plan_id" in _table_columns(connection, "tasks")
        assert {
            "visual_role",
            "claim_refs",
            "source_refs",
            "production_metadata",
        } <= _table_columns(connection, "scenes")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_existing_release_database_upgrades_and_downgrades_trend_center(tmp_path: Path):
    database_file, database_url = _migration_database(tmp_path, "upgrade.db")

    _run_migration(database_url, BASELINE_REVISION)
    with sqlite3.connect(database_file) as connection:
        assert _migration_version(connection) == BASELINE_REVISION
        assert "trend_runs" not in _table_names(connection)
        connection.execute(
            """
            INSERT INTO projects
                (id, name, description, aspect_ratio, status, settings, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("project_legacy", "Legacy", "", "9:16", "draft", "{}", "2026-09-18", "2026-09-18"),
        )
        connection.execute(
            """
            INSERT INTO tasks
                (id, project_id, title, description, job_type, status, progress_percentage,
                 input_payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "task_legacy",
                "project_legacy",
                "Legacy task",
                "",
                "video_composition",
                "pending",
                0,
                "{}",
                "2026-09-18",
                "2026-09-18",
            ),
        )
        connection.commit()

    _run_migration(database_url, "head")
    with sqlite3.connect(database_file) as connection:
        assert _migration_version(connection) == RELEASE_REVISION
        assert "trend_runs" in _table_names(connection)
        assert "primary_production_mode" in _table_columns(connection, "projects")
        assert "production_mode" in _table_columns(connection, "tasks")
        assert {"product_id", "creative_angle"} <= _table_columns(connection, "tasks")
        assert {"products", "product_assets", "commerce_creative_plans"} <= _table_names(connection)
        assert {
            "drama_bibles",
            "drama_characters",
            "drama_locations",
            "drama_episodes",
            "drama_scenes",
            "drama_shots",
            "drama_dialogue_lines",
        } <= _table_names(connection)
        assert "creative_plan_id" in _table_columns(connection, "tasks")
        assert {
            "visual_role",
            "claim_refs",
            "source_refs",
            "production_metadata",
        } <= _table_columns(connection, "scenes")
        assert connection.execute(
            "SELECT primary_production_mode FROM projects WHERE id = 'project_legacy'"
        ).fetchone() == ("knowledge",)
        assert connection.execute(
            "SELECT production_mode FROM tasks WHERE id = 'task_legacy'"
        ).fetchone() == ("knowledge",)

    _run_migration(database_url, BASELINE_REVISION, downgrade=True)
    with sqlite3.connect(database_file) as connection:
        assert _migration_version(connection) == BASELINE_REVISION
        assert not {
            "trend_runs",
            "trend_source_runs",
            "trend_items",
            "trend_observations",
            "trend_project_matches",
            "topic_proposals",
            "trend_subscriptions",
        } & _table_names(connection)

@pytest.mark.asyncio
async def test_verify_schema_reports_missing_columns(tmp_path: Path):
    database_file, _ = _migration_database(tmp_path, "incomplete.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_file}")

    async with engine.begin() as connection:
        for table_name in (
            "alembic_version",
            "projects",
            "project_templates",
            "tasks",
            "workflow_jobs",
            "workflow_step_runs",
            "workflow_artifacts",
            "workflow_step_artifacts",
            "job_events",
            "assets",
            "scenes",
            "credentials",
            "social_accounts",
            "publishing_jobs",
            "provider_configs",
        ):
            await connection.exec_driver_sql(
                f'CREATE TABLE "{table_name}" (id VARCHAR(36) PRIMARY KEY)'
            )

    missing = await verify_schema(engine)
    assert "project_templates.template_id" in missing
    assert "provider_configs.last_test_connected" in missing
    assert "workflow_jobs.lease_token" in missing
    assert "projects.primary_production_mode" in missing
    assert "tasks.production_mode" in missing
    assert "scenes.visual_role" in missing
    assert "scenes.claim_refs" in missing
    assert "scenes.source_refs" in missing
    assert "scenes.production_metadata" in missing
    assert "workflow_step_runs.input_fingerprint" in missing
    assert "prompt_call_observations" in missing

    await engine.dispose()
