from __future__ import annotations

import json
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
RELEASE_REVISION = "012_project_context_versions"


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


def _assert_current_schema(connection: sqlite3.Connection) -> None:
    assert _table_names(connection) == set(Base.metadata.tables) | {"alembic_version"}
    for table in Base.metadata.tables.values():
        assert _table_columns(connection, table.name) == {
            column.name for column in table.columns
        }
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_head_creates_current_schema(tmp_path: Path):
    database_file, database_url = _migration_database(tmp_path, "release.db")

    _run_migration(database_url, "head")

    with sqlite3.connect(database_file) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            RELEASE_REVISION,
        )
        _assert_current_schema(connection)


def test_baseline_database_upgrades_and_downgrades_current_schema(tmp_path: Path):
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
            (
                "project_legacy",
                "Legacy",
                "",
                "9:16",
                "draft",
                json.dumps({"content_brief": {"goal": "旧目标", "key_points": ["旧主张"]}}),
                "2026-09-18",
                "2026-09-18",
            ),
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
                json.dumps(
                    {
                        "content_brief": {"angle": "先定义", "key_points": ["旧主张"]},
                        "template_id": "default_portrait",
                        "product_id": "product_legacy",
                        "creative_plan_id": "plan_legacy",
                        "creative_angle": "demo",
                        "visual_mode": "video",
                        "commerce": {"product_id": "product_legacy", "variant_label": "旧方案"},
                        "image_workflow_id": "image_flux.json",
                        "video_workflow_id": "selfhost/video_wan2.1_fusionx.json",
                        "image_workflow_snapshot": {
                            "id": "image_flux.json",
                            "path": "image_flux.json",
                        },
                        "voice_speed": 1.15,
                    }
                ),
                "2026-09-18",
                "2026-09-18",
            ),
        )
        connection.execute(
            """
            INSERT INTO provider_configs
                (id, provider_type, provider_name, display_name, enabled, is_default,
                 config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "provider_legacy_tts",
                "tts",
                "volcengine",
                "Legacy TTS",
                1,
                1,
                json.dumps(
                    {
                        "resource_id": "volc.service_type.10029",
                        "default_voice": "zh_female_cancan_mars_bigtts",
                    }
                ),
                "2026-09-18",
                "2026-09-18",
            ),
        )
        connection.execute(
            """
            INSERT INTO provider_configs
                (id, provider_type, provider_name, display_name, enabled, is_default,
                 config, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "provider_legacy_image",
                "image",
                "comfyui",
                "Legacy Image",
                1,
                1,
                json.dumps({"default_workflow": "image_flux.json"}),
                "2026-09-18",
                "2026-09-18",
            ),
        )
        connection.commit()

    _run_migration(database_url, "002_trend_center")
    with sqlite3.connect(database_file) as connection:
        connection.execute(
            """
            INSERT INTO trend_items (id, canonical_key, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("trend_item_legacy", "legacy-speed", "旧速度", "2026-09-18", "2026-09-18"),
        )
        connection.execute(
            """
            INSERT INTO topic_proposals
                (id, project_id, trend_item_id, revision, status, title, angle,
                 match_reason, matched_keywords, trend_snapshot, content_brief,
                 generation_options, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "proposal_legacy_speed",
                "project_legacy",
                "trend_item_legacy",
                1,
                "draft",
                "旧速度提案",
                "旧角度",
                "旧匹配",
                json.dumps([]),
                json.dumps({}),
                json.dumps({"thesis": "旧主张"}),
                json.dumps({"voice_speed": 1.25}),
                "2026-09-18",
                "2026-09-18",
            ),
        )
        connection.commit()

    _run_migration(database_url, "head")
    with sqlite3.connect(database_file) as connection:
        assert _migration_version(connection) == RELEASE_REVISION
        _assert_current_schema(connection)
        assert connection.execute(
            "SELECT primary_production_mode FROM projects WHERE id = 'project_legacy'"
        ).fetchone() == ("knowledge",)
        assert connection.execute(
            "SELECT production_mode FROM tasks WHERE id = 'task_legacy'"
        ).fetchone() == ("knowledge",)
        assert connection.execute(
            "SELECT context_hash FROM tasks WHERE id = 'task_legacy'"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT COUNT(*) FROM project_context_versions WHERE project_id = 'project_legacy'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM knowledge_content_items WHERE project_id = 'project_legacy'"
        ).fetchone()[0] >= 1
        settings_value, payload_value = connection.execute(
            "SELECT settings, input_payload FROM projects "
            "JOIN tasks ON tasks.project_id = projects.id WHERE projects.id = 'project_legacy'"
        ).fetchone()
        settings = json.loads(settings_value)
        payload = json.loads(payload_value)
        assert "content_brief" not in settings
        assert settings["knowledge_brief"]["viewer_takeaway"] == "旧目标"
        assert "content_brief" not in payload
        assert payload["knowledge_brief"]["thesis"] == "先定义"
        assert payload["knowledge_brief"]["key_claims"][0]["statement"] == "旧主张"
        assert payload["template_id"] == "image_gallery_matted"
        assert payload["content_mode"] == "generated_video"
        assert not {"product_id", "creative_plan_id", "creative_angle", "visual_mode", "commerce"} & payload.keys()
        assert payload["image_workflow_id"] == "image/image_flux.json"
        assert payload["video_workflow_id"] == "video/video_wan2.1_fusionx.json"
        assert payload["image_workflow_snapshot"] == {
            "id": "image/image_flux.json",
            "path": "image/image_flux.json",
        }
        assert payload["speed"] == 1.15
        assert "voice_speed" not in payload
        provider_config = json.loads(
            connection.execute(
                "SELECT config FROM provider_configs WHERE id = 'provider_legacy_tts'"
            ).fetchone()[0]
        )
        assert provider_config == {
            "resource_id": "seed-tts-2.0",
            "default_voice": "zh_female_vv_uranus_bigtts",
        }
        image_provider_config = json.loads(
            connection.execute(
                "SELECT config FROM provider_configs WHERE id = 'provider_legacy_image'"
            ).fetchone()[0]
        )
        assert image_provider_config == {"default_workflow": "image/image_flux.json"}

    with sqlite3.connect(database_file) as connection:
        proposal_options = json.loads(
            connection.execute(
                "SELECT generation_options FROM topic_proposals WHERE id = 'proposal_legacy_speed'"
            ).fetchone()[0]
        )
        assert proposal_options == {"speed": 1.25}

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
