from collections.abc import AsyncGenerator

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models"""


connect_args = {"timeout": 30.0} if "sqlite" in settings.database_url else {}

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    connect_args=connect_args,
)


if "sqlite" in settings.database_url:

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


_REQUIRED_TABLES = {
    "alembic_version",
    "projects",
    "project_templates",
    "tasks",
    "workflow_jobs",
    "job_events",
    "workflow_step_runs",
    "workflow_artifacts",
    "workflow_step_artifacts",
    "assets",
    "scenes",
    "credentials",
    "social_accounts",
    "publishing_jobs",
    "provider_configs",
    "prompt_call_observations",
    "trend_runs",
    "trend_source_runs",
    "trend_items",
    "trend_observations",
    "trend_project_matches",
    "topic_proposals",
    "trend_subscriptions",
    "products",
    "product_assets",
    "commerce_creative_plans",
    "drama_bibles",
    "drama_characters",
    "drama_locations",
    "drama_episodes",
    "drama_scenes",
    "drama_shots",
    "drama_dialogue_lines",
}

_REQUIRED_COLUMNS = {
    "projects": {"primary_production_mode"},
    "tasks": {"production_mode", "product_id", "creative_angle", "creative_plan_id"},
    "products": {"title", "source_snapshot", "truth_sheet"},
    "product_assets": {"product_id", "asset_id", "source_kind"},
    "scenes": {"visual_role", "claim_refs", "source_refs", "production_metadata"},
    "workflow_jobs": {"lease_token"},
    "workflow_step_runs": {"input_fingerprint", "output_payload", "validity"},
    "project_templates": {"template_id", "template_version"},
    "provider_configs": {
        "last_test_connected",
        "last_tested_at",
        "last_test_message",
        "last_test_latency_ms",
    },
    "drama_bibles": {"project_id", "current_stage", "stage_state", "checkpoint"},
    "drama_characters": {"bible_id", "appearance_lock", "prompt_anchor", "approval_status"},
    "drama_locations": {"bible_id", "visual_description", "reference_asset_ids", "approval_status"},
    "drama_episodes": {"bible_id", "episode_number", "approval_status", "checkpoint"},
    "drama_scenes": {"episode_id", "approval_status"},
    "drama_shots": {
        "scene_id",
        "character_ids",
        "duration_hint",
        "prompt_anchor",
        "approval_status",
    },
    "drama_dialogue_lines": {"shot_id", "speaker_name", "text"},
}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for database session"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_schema(database_engine: AsyncEngine | None = None) -> list[str]:
    """Return missing required tables or columns without mutating the database."""

    target_engine = database_engine or engine

    def inspect_schema(connection):
        inspector = inspect(connection)
        existing_tables = set(inspector.get_table_names())
        missing = sorted(_REQUIRED_TABLES - existing_tables)

        for table_name, required_columns in _REQUIRED_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing.extend(
                f"{table_name}.{column_name}"
                for column_name in sorted(required_columns - existing_columns)
            )

        return missing

    async with target_engine.connect() as conn:
        return await conn.run_sync(inspect_schema)
