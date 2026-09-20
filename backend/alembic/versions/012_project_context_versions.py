"""Add immutable Project context snapshots and typed Knowledge items.

Revision ID: 012_project_context_versions
Revises: 011_canonicalize_production_contracts
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "012_project_context_versions"
down_revision: str | None = "011_canonicalize_production_contracts"
branch_labels: str | None = None
depends_on: str | None = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def _knowledge_brief(settings: dict[str, Any]) -> dict[str, Any]:
    brief = settings.get("knowledge_brief")
    return brief if isinstance(brief, dict) else {}


def upgrade() -> None:
    op.create_table(
        "project_context_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("context_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_project_context_version"),
        sa.UniqueConstraint("project_id", "context_hash", name="uq_project_context_hash"),
    )
    op.create_index(
        "ix_project_context_versions_project_version",
        "project_context_versions",
        ["project_id", "version"],
        unique=False,
    )
    op.create_index(
        "ix_project_context_versions_hash",
        "project_context_versions",
        ["context_hash"],
        unique=False,
    )

    op.create_table(
        "knowledge_project_profiles",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("positioning", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("default_audience", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=255), nullable=False),
        sa.Column("visual_system", sa.JSON(), nullable=False),
        sa.Column("evidence_strategy", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "commerce_project_profiles",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("market", sa.String(length=255), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("marketing_goal", sa.Text(), nullable=False),
        sa.Column("brand_tone", sa.String(length=255), nullable=False),
        sa.Column("visual_system", sa.JSON(), nullable=False),
        sa.Column("default_cta", sa.Text(), nullable=False),
        sa.Column("compliance_limits", sa.JSON(), nullable=False),
        sa.Column("platform_defaults", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "knowledge_content_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("takeaway", sa.Text(), nullable=False),
        sa.Column("genre", sa.String(length=100), nullable=False),
        sa.Column("key_claims", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_content_items_project_id",
        "knowledge_content_items",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_content_items_project_status",
        "knowledge_content_items",
        ["project_id", "review_status"],
        unique=False,
    )

    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("project_context_version_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("context_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("knowledge_item_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("drama_episode_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_project_context_version_id",
            "project_context_versions",
            ["project_context_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_tasks_knowledge_item_id",
            "knowledge_content_items",
            ["knowledge_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_tasks_drama_episode_id",
            "drama_episodes",
            ["drama_episode_id"],
            ["id"],
            ondelete="SET NULL",
        )
    for name, columns in (
        ("ix_tasks_project_context_version_id", ["project_context_version_id"]),
        ("ix_tasks_context_hash", ["context_hash"]),
        ("ix_tasks_knowledge_item_id", ["knowledge_item_id"]),
        ("ix_tasks_drama_episode_id", ["drama_episode_id"]),
    ):
        op.create_index(name, "tasks", columns, unique=False)

    bind = op.get_bind()
    projects = sa.table(
        "projects",
        sa.column("id", sa.String(length=36)),
        sa.column("name", sa.String(length=255)),
        sa.column("description", sa.Text()),
        sa.column("aspect_ratio", sa.String(length=10)),
        sa.column("primary_production_mode", sa.String(length=20)),
        sa.column("default_voice_id", sa.String(length=100)),
        sa.column("bgm_asset_id", sa.String(length=36)),
        sa.column("settings", sa.JSON()),
    )
    tasks = sa.table(
        "tasks",
        sa.column("id", sa.String(length=36)),
        sa.column("project_id", sa.String(length=36)),
        sa.column("title", sa.String(length=255)),
        sa.column("production_mode", sa.String(length=20)),
        sa.column("input_payload", sa.JSON()),
        sa.column("product_id", sa.String(length=36)),
        sa.column("creative_plan_id", sa.String(length=36)),
        sa.column("project_context_version_id", sa.String(length=36)),
        sa.column("context_hash", sa.String(length=64)),
        sa.column("knowledge_item_id", sa.String(length=36)),
        sa.column("drama_episode_id", sa.String(length=36)),
    )
    profiles = sa.table(
        "knowledge_project_profiles",
        sa.column("project_id", sa.String(length=36)),
        sa.column("positioning", sa.Text()),
        sa.column("domain", sa.String(length=255)),
        sa.column("default_audience", sa.Text()),
        sa.column("tone", sa.String(length=255)),
        sa.column("visual_system", sa.JSON()),
        sa.column("evidence_strategy", sa.JSON()),
        sa.column("revision", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    commerce_profiles = sa.table(
        "commerce_project_profiles",
        sa.column("project_id", sa.String(length=36)),
        sa.column("brand", sa.String(length=255)),
        sa.column("market", sa.String(length=255)),
        sa.column("audience", sa.Text()),
        sa.column("marketing_goal", sa.Text()),
        sa.column("brand_tone", sa.String(length=255)),
        sa.column("visual_system", sa.JSON()),
        sa.column("default_cta", sa.Text()),
        sa.column("compliance_limits", sa.JSON()),
        sa.column("platform_defaults", sa.JSON()),
        sa.column("revision", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    content_items = sa.table(
        "knowledge_content_items",
        sa.column("id", sa.String(length=36)),
        sa.column("project_id", sa.String(length=36)),
        sa.column("topic", sa.String(length=500)),
        sa.column("audience", sa.Text()),
        sa.column("thesis", sa.Text()),
        sa.column("takeaway", sa.Text()),
        sa.column("genre", sa.String(length=100)),
        sa.column("key_claims", sa.JSON()),
        sa.column("source_refs", sa.JSON()),
        sa.column("review_status", sa.String(length=30)),
        sa.column("revision", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    contexts = sa.table(
        "project_context_versions",
        sa.column("id", sa.String(length=36)),
        sa.column("project_id", sa.String(length=36)),
        sa.column("version", sa.Integer()),
        sa.column("context_hash", sa.String(length=64)),
        sa.column("context_payload", sa.JSON()),
        sa.column("created_at", sa.DateTime()),
    )
    drama_episodes = sa.table(
        "drama_episodes",
        sa.column("id", sa.String(length=36)),
        sa.column("bible_id", sa.String(length=36)),
    )
    drama_bibles = sa.table(
        "drama_bibles",
        sa.column("id", sa.String(length=36)),
        sa.column("project_id", sa.String(length=36)),
    )

    project_rows = bind.execute(
        sa.select(
            projects.c.id,
            projects.c.name,
            projects.c.description,
            projects.c.aspect_ratio,
            projects.c.primary_production_mode,
            projects.c.default_voice_id,
            projects.c.bgm_asset_id,
            projects.c.settings,
        )
    ).all()
    task_rows = bind.execute(
        sa.select(
            tasks.c.id,
            tasks.c.project_id,
            tasks.c.title,
            tasks.c.production_mode,
            tasks.c.input_payload,
            tasks.c.product_id,
            tasks.c.creative_plan_id,
        )
    ).all()
    tasks_by_project: dict[str, list[Any]] = {}
    for row in task_rows:
        tasks_by_project.setdefault(row.project_id, []).append(row)

    for project in project_rows:
        mode = project.primary_production_mode or "knowledge"
        settings = _as_dict(project.settings)
        brief = _knowledge_brief(settings)
        if mode == "knowledge":
            profile_id = project.id
            bind.execute(
                profiles.insert().values(
                    project_id=profile_id,
                    positioning=str(brief.get("thesis") or ""),
                    domain=str(brief.get("domain") or ""),
                    default_audience=str(brief.get("audience") or ""),
                    tone=str(brief.get("tone") or ""),
                    visual_system={},
                    evidence_strategy={"source_refs": brief.get("source_refs") or []},
                    revision=1,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
        elif mode == "commerce":
            commerce = _as_dict(settings.get("commerce_profile"))
            bind.execute(
                commerce_profiles.insert().values(
                    project_id=project.id,
                    brand=str(commerce.get("brand") or ""),
                    market=str(commerce.get("market") or ""),
                    audience=str(commerce.get("audience") or ""),
                    marketing_goal=str(commerce.get("marketing_goal") or ""),
                    brand_tone=str(commerce.get("brand_tone") or ""),
                    visual_system=commerce.get("visual_system") or {},
                    default_cta=str(commerce.get("default_cta") or ""),
                    compliance_limits=commerce.get("compliance_limits") or [],
                    platform_defaults=commerce.get("platform_defaults") or {},
                    revision=1,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )

        project_items: list[dict[str, Any]] = []
        for task in tasks_by_project.get(project.id, []):
            payload = _as_dict(task.input_payload)
            if mode == "knowledge":
                knowledge = _as_dict(payload.get("knowledge_brief"))
                item_id = _stable_id("knowledge", task.id)
                item = {
                    "id": item_id,
                    "project_id": project.id,
                    "topic": str(payload.get("topic") or task.title or project.name),
                    "audience": str(knowledge.get("audience") or ""),
                    "thesis": str(knowledge.get("thesis") or ""),
                    "takeaway": str(knowledge.get("viewer_takeaway") or knowledge.get("takeaway") or ""),
                    "genre": str(knowledge.get("genre") or "auto"),
                    "key_claims": knowledge.get("key_claims") or [],
                    "source_refs": knowledge.get("source_refs") or [],
                    "review_status": "legacy",
                    "revision": 1,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                bind.execute(content_items.insert().values(**item))
                bind.execute(
                    tasks.update().where(tasks.c.id == task.id).values(knowledge_item_id=item_id)
                )
                project_items.append({key: item[key] for key in (
                    "id", "topic", "audience", "thesis", "takeaway", "genre", "key_claims", "source_refs", "review_status", "revision"
                )})

            if mode == "drama":
                episode_id = payload.get("episode_id")
                if not episode_id:
                    drama_payload = payload.get("drama")
                    episode_id = drama_payload.get("episode_id") if isinstance(drama_payload, dict) else None
                if episode_id:
                    exists = bind.execute(
                        sa.select(drama_episodes.c.id)
                        .select_from(
                            drama_episodes.join(
                                drama_bibles,
                                drama_episodes.c.bible_id == drama_bibles.c.id,
                            )
                        )
                        .where(
                            drama_episodes.c.id == str(episode_id),
                            drama_bibles.c.project_id == project.id,
                        )
                    ).scalar_one_or_none()
                    if exists:
                        bind.execute(
                            tasks.update().where(tasks.c.id == task.id).values(drama_episode_id=str(episode_id))
                        )

        context_payload = {
            "schema_version": 1,
            "production_mode": mode,
            "project": {
                "name": project.name,
                "description": project.description or "",
                "aspect_ratio": project.aspect_ratio,
                "default_voice_id": project.default_voice_id,
                "bgm_asset_id": project.bgm_asset_id,
                "settings": settings,
            },
            "profile": (
                {
                    "positioning": str(brief.get("thesis") or ""),
                    "domain": str(brief.get("domain") or ""),
                    "default_audience": str(brief.get("audience") or ""),
                    "tone": str(brief.get("tone") or ""),
                }
                if mode == "knowledge"
                else _as_dict(settings.get("commerce_profile"))
                if mode == "commerce"
                else None
            ),
            "content_items": project_items if mode == "knowledge" else [],
            "resource_refs": [
                {
                    "product_id": str(row.product_id) if row.product_id else None,
                    "creative_plan_id": str(row.creative_plan_id) if row.creative_plan_id else None,
                }
                for row in tasks_by_project.get(project.id, [])
                if mode == "commerce" and (row.product_id or row.creative_plan_id)
            ],
        }
        context_id = _stable_id("ctx", project.id)
        digest = _hash(context_payload)
        bind.execute(
            contexts.insert().values(
                id=context_id,
                project_id=project.id,
                version=1,
                context_hash=digest,
                context_payload=context_payload,
                created_at=_now(),
            )
        )
        bind.execute(
            tasks.update()
            .where(tasks.c.project_id == project.id)
            .values(project_context_version_id=context_id, context_hash=digest)
        )

    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_tasks_project_mode_reference_shape",
            "(production_mode = 'knowledge' AND product_id IS NULL AND creative_plan_id IS NULL AND drama_episode_id IS NULL) OR "
            "(production_mode = 'commerce' AND knowledge_item_id IS NULL AND drama_episode_id IS NULL) OR "
            "(production_mode = 'drama' AND knowledge_item_id IS NULL AND product_id IS NULL AND creative_plan_id IS NULL AND drama_episode_id IS NOT NULL)",
        )
    with op.batch_alter_table("projects", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_projects_primary_production_mode",
            "primary_production_mode IN ('knowledge', 'commerce', 'drama')",
        )


def downgrade() -> None:
    for name in (
        "ix_tasks_drama_episode_id",
        "ix_tasks_knowledge_item_id",
        "ix_tasks_context_hash",
        "ix_tasks_project_context_version_id",
    ):
        op.drop_index(name, table_name="tasks")
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_tasks_project_mode_reference_shape", type_="check")
        batch_op.drop_constraint("fk_tasks_drama_episode_id", type_="foreignkey")
        batch_op.drop_constraint("fk_tasks_knowledge_item_id", type_="foreignkey")
        batch_op.drop_constraint("fk_tasks_project_context_version_id", type_="foreignkey")
        batch_op.drop_column("drama_episode_id")
        batch_op.drop_column("knowledge_item_id")
        batch_op.drop_column("context_hash")
        batch_op.drop_column("project_context_version_id")
    with op.batch_alter_table("projects", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_projects_primary_production_mode", type_="check")
    op.drop_index("ix_knowledge_content_items_project_status", table_name="knowledge_content_items")
    op.drop_index("ix_knowledge_content_items_project_id", table_name="knowledge_content_items")
    op.drop_table("knowledge_content_items")
    op.drop_table("commerce_project_profiles")
    op.drop_table("knowledge_project_profiles")
    op.drop_index("ix_project_context_versions_hash", table_name="project_context_versions")
    op.drop_index("ix_project_context_versions_project_version", table_name="project_context_versions")
    op.drop_table("project_context_versions")
