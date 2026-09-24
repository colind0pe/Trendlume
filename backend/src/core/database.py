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
    "project_asset_bindings",
    "production_context_snapshots",
    "knowledge_task_details",
    "commerce_task_details",
    "drama_task_episodes",
    "drama_project_profiles",
    "drama_style_guides",
    "drama_characters",
    "drama_locations",
    "drama_props",
    "drama_task_scenes",
    "drama_task_shots",
    "drama_task_dialogue_lines",
    "knowledge_project_profiles",
    "commerce_project_profiles",
}

_REQUIRED_COLUMNS = {
    "projects": {"mode", "default_production_settings"},
    "tasks": {"project_id", "editorial_status", "production_status", "generation_settings"},
    "products": {"title", "source_snapshot", "truth_sheet"},
    "product_assets": {"product_id", "asset_id", "source_kind"},
    "scenes": {"visual_role", "claim_refs", "source_refs", "production_metadata"},
    "workflow_jobs": {"lease_token", "production_context_snapshot_id"},
    "workflow_step_runs": {"input_fingerprint", "output_payload", "validity"},
    "project_templates": {"template_id", "template_version"},
    "provider_configs": {
        "last_test_connected",
        "last_tested_at",
        "last_test_message",
        "last_test_latency_ms",
    },
    "production_context_snapshots": {"task_id", "project_id", "mode", "context_hash", "context_payload"},
    "knowledge_project_profiles": {"project_id", "positioning", "evidence_strategy"},
    "commerce_project_profiles": {"project_id", "brand", "marketing_goal", "platform_defaults"},
    "knowledge_task_details": {"task_id", "topic", "claims", "sources", "review_status"},
    "commerce_task_details": {"task_id", "creative_angle", "product_facts_version"},
    "drama_task_episodes": {"task_id", "project_id", "episode_number", "review_status"},
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
        if "alembic_version" in existing_tables:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
            if revision != "001":
                missing.append(
                    f"unsupported database revision {revision or 'none'}; recreate the database with revision 001"
                )

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
