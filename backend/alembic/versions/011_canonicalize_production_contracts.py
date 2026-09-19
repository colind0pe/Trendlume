"""Create and canonicalize the current Production Mode schema."""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "011_canonicalize_production_contracts"
down_revision: str | None = "002_trend_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TASK_COLUMN_KEYS = {
    "production_mode",
    "product_id",
    "creative_plan_id",
    "creative_angle",
}

TEMPLATE_ALIASES = {
    "default_portrait": "image_gallery_matted",
    "default_landscape": "image_wide_minimal",
    "default_square": "image_square_matted",
    "video_default_portrait": "video_full_overlay",
    "video_default_landscape": "video_wide_full",
    "video_default_square": "video_square_full",
    "image_default": "image_gallery_matted",
    "video_default": "video_full_overlay",
    "static_default": "static_editorial_quote",
}

WORKFLOW_PATH_ALIASES = {
    "analyse_image.json": "analysis/analyse_image.json",
    "analyse_video.json": "analysis/analyse_video.json",
    "tts_edge.json": "audio/tts_edge.json",
    "tts_index2.json": "audio/tts_index2.json",
    "image_flux.json": "image/image_flux.json",
    "image_nano_banana.json": "image/image_nano_banana.json",
    "image_qwen.json": "image/image_qwen.json",
    "image_z_image_turbo.json": "image/image_z_image_turbo.json",
    "image_z_image.json": "image/image_z_image.json",
    "video_wan2.1_fusionx.json": "video/video_wan2.1_fusionx.json",
    "selfhost/video_wan2.1_fusionx.json": "video/video_wan2.1_fusionx.json",
}
CANONICAL_WORKFLOW_PATHS = set(WORKFLOW_PATH_ALIASES.values())

LEGACY_VOLCENGINE_RESOURCE_ID = "volc.service_type.10029"
LEGACY_VOLCENGINE_VOICE = "zh_female_cancan_mars_bigtts"
CURRENT_VOLCENGINE_RESOURCE_ID = "seed-tts-2.0"
CURRENT_VOLCENGINE_VOICE = "zh_female_vv_uranus_bigtts"


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _knowledge_brief(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    source_refs = [
        str(ref).strip()
        for ref in source.get("source_refs") or []
        if str(ref).strip()
    ][:20]
    claims = source.get("key_claims") or []
    if not claims:
        claims = source.get("claims") or source.get("key_points") or []
    normalized_claims = []
    for index, claim in enumerate(claims[:20]):
        if isinstance(claim, dict):
            statement = claim.get("statement") or claim.get("text") or ""
            claim_refs = claim.get("source_refs") or source_refs
        else:
            statement = claim
            claim_refs = source_refs
        statement = str(statement).strip()[:1000]
        if statement:
            normalized_claims.append(
                {
                    "id": str(
                        claim.get("id") if isinstance(claim, dict) else ""
                    ).strip()
                    or f"claim-{index + 1}",
                    "statement": statement,
                    "source_refs": [
                        str(ref).strip()
                        for ref in claim_refs
                        if str(ref).strip()
                    ][:20],
                }
            )
    return {
        "audience": str(source.get("audience") or "").strip()[:500],
        "thesis": str(
            source.get("thesis") or source.get("angle") or source.get("goal") or ""
        ).strip()[:500],
        "viewer_takeaway": str(
            source.get("viewer_takeaway")
            or source.get("goal")
            or source.get("thesis")
            or ""
        ).strip()[:500],
        "key_claims": normalized_claims,
        "source_refs": list(dict.fromkeys(source_refs)),
        "genre": str(source.get("genre") or "auto").strip()[:100],
    }


def _canonical_workflow_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.strip().replace("\\", "/")
    if normalized in CANONICAL_WORKFLOW_PATHS:
        return normalized
    return WORKFLOW_PATH_ALIASES.get(normalized, value)


def _canonicalize_brief_container(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    legacy_brief = normalized.pop("content_brief", None)
    if "knowledge_brief" in normalized:
        normalized["knowledge_brief"] = _knowledge_brief(
            normalized["knowledge_brief"]
        )
    elif legacy_brief is not None:
        normalized["knowledge_brief"] = _knowledge_brief(legacy_brief)
    return normalized


def _canonicalize_speed(value: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(value)
    legacy_speed = normalized.pop("voice_speed", None)
    if "speed" not in normalized and legacy_speed is not None:
        normalized["speed"] = legacy_speed
    return normalized


def _canonicalize_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _canonicalize_brief_container(
        {key: value for key, value in payload.items() if key not in TASK_COLUMN_KEYS}
    )

    visual_mode = normalized.pop("visual_mode", None)
    if "content_mode" not in normalized and visual_mode in {"image", "video"}:
        normalized["content_mode"] = (
            "generated_video" if visual_mode == "video" else "generated_image"
        )
    normalized.pop("commerce", None)

    normalized = _canonicalize_speed(normalized)

    template_id = normalized.get("template_id")
    if template_id in TEMPLATE_ALIASES:
        normalized["template_id"] = TEMPLATE_ALIASES[template_id]

    for key in ("image_workflow_id", "video_workflow_id"):
        if key in normalized:
            normalized[key] = _canonical_workflow_path(normalized[key])
    for key in ("image_workflow_snapshot", "video_workflow_snapshot"):
        snapshot = normalized.get(key)
        if not isinstance(snapshot, dict):
            continue
        snapshot = dict(snapshot)
        for field in ("id", "path"):
            if field in snapshot:
                snapshot[field] = _canonical_workflow_path(snapshot[field])
        normalized[key] = snapshot
    return normalized


def _canonicalize_generation_options(value: Any) -> dict[str, Any]:
    return _canonicalize_speed(_as_dict(value))


def _canonicalize_provider_config(
    provider_type: str, provider_name: str, value: Any
) -> dict[str, Any]:
    config = _as_dict(value)
    normalized = dict(config)
    if provider_type == "tts" and provider_name == "volcengine":
        resource_id = str(config.get("resource_id") or "").strip()
        voice = str(config.get("default_voice") or "").strip()
        if resource_id == LEGACY_VOLCENGINE_RESOURCE_ID and voice in {
            "",
            LEGACY_VOLCENGINE_VOICE,
        }:
            normalized["resource_id"] = CURRENT_VOLCENGINE_RESOURCE_ID
            normalized["default_voice"] = CURRENT_VOLCENGINE_VOICE
    if provider_type in {"image", "video"} and provider_name == "comfyui":
        if "default_workflow" in config:
            normalized["default_workflow"] = _canonical_workflow_path(
                config["default_workflow"]
            )
    return normalized


def _canonicalize_data() -> None:
    bind = op.get_bind()
    templates = sa.table(
        "project_templates",
        sa.column("id", sa.String(length=36)),
        sa.column("template_id", sa.String(length=255)),
    )
    for old_id, new_id in TEMPLATE_ALIASES.items():
        bind.execute(
            templates.update()
            .where(templates.c.template_id == old_id)
            .values(template_id=new_id)
        )

    projects = sa.table(
        "projects",
        sa.column("id", sa.String(length=36)),
        sa.column("settings", sa.JSON()),
    )
    for project_id, raw_settings in bind.execute(
        sa.select(projects.c.id, projects.c.settings)
    ).all():
        settings = _as_dict(raw_settings)
        normalized = _canonicalize_brief_container(settings)
        if normalized != settings:
            bind.execute(
                projects.update()
                .where(projects.c.id == project_id)
                .values(settings=normalized)
            )

    tasks = sa.table(
        "tasks",
        sa.column("id", sa.String(length=36)),
        sa.column("input_payload", sa.JSON()),
    )
    for task_id, raw_payload in bind.execute(
        sa.select(tasks.c.id, tasks.c.input_payload)
    ).all():
        payload = _as_dict(raw_payload)
        normalized = _canonicalize_task_payload(payload)
        if normalized != payload:
            bind.execute(
                tasks.update()
                .where(tasks.c.id == task_id)
                .values(input_payload=normalized)
            )

    proposals = sa.table(
        "topic_proposals",
        sa.column("id", sa.String(length=36)),
        sa.column("knowledge_brief", sa.JSON()),
        sa.column("generation_options", sa.JSON()),
    )
    for proposal_id, raw_brief, raw_options in bind.execute(
        sa.select(
            proposals.c.id,
            proposals.c.knowledge_brief,
            proposals.c.generation_options,
        )
    ).all():
        brief = _knowledge_brief(raw_brief)
        options = _canonicalize_generation_options(raw_options)
        if brief != _as_dict(raw_brief) or options != _as_dict(raw_options):
            bind.execute(
                proposals.update()
                .where(proposals.c.id == proposal_id)
                .values(knowledge_brief=brief, generation_options=options)
            )

    providers = sa.table(
        "provider_configs",
        sa.column("id", sa.String(length=36)),
        sa.column("provider_type", sa.String(length=32)),
        sa.column("provider_name", sa.String(length=64)),
        sa.column("config", sa.JSON()),
    )
    for provider_id, provider_type, provider_name, raw_config in bind.execute(
        sa.select(
            providers.c.id,
            providers.c.provider_type,
            providers.c.provider_name,
            providers.c.config,
        )
    ).all():
        config = _as_dict(raw_config)
        normalized = _canonicalize_provider_config(
            provider_type, provider_name, config
        )
        if normalized != config:
            bind.execute(
                providers.update()
                .where(providers.c.id == provider_id)
                .values(config=normalized)
            )


def upgrade() -> None:
    default = sa.text("'knowledge'")
    op.add_column(
        "projects",
        sa.Column(
            "primary_production_mode",
            sa.String(length=20),
            nullable=False,
            server_default=default,
        ),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "production_mode",
            sa.String(length=20),
            nullable=False,
            server_default=default,
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "visual_role",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'concept'"),
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "claim_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "source_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "scenes",
        sa.Column(
            "production_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=20), nullable=False),
        sa.Column("specifications", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("truth_sheet", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_updated_at", "products", ["updated_at"], unique=False)

    op.create_table(
        "product_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("asset_type", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("alt_text", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_assets_product_order",
        "product_assets",
        ["product_id", "sort_order"],
        unique=False,
    )

    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("creative_angle", sa.String(length=30), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_product_id",
            "products",
            ["product_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_tasks_product_id", "tasks", ["product_id"], unique=False)

    op.create_table(
        "commerce_creative_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("source_plan_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("variant_label", sa.String(length=100), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column("angle", sa.String(length=30), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("core_message", sa.Text(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("scene_outline", sa.JSON(), nullable=False),
        sa.Column("cta", sa.Text(), nullable=False),
        sa.Column("truth_sheet_version", sa.Integer(), nullable=False),
        sa.Column("fact_snapshot", sa.JSON(), nullable=False),
        sa.Column("selected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_plan_id"],
            ["commerce_creative_plans.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commerce_creative_plans_product_id",
        "commerce_creative_plans",
        ["product_id"],
        unique=False,
    )
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("creative_plan_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_creative_plan_id",
            "commerce_creative_plans",
            ["creative_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_tasks_creative_plan_id", "tasks", ["creative_plan_id"], unique=False)

    op.create_table(
        "drama_bibles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("logline", sa.Text(), nullable=False),
        sa.Column("genre", sa.String(length=100), nullable=False),
        sa.Column("tone", sa.String(length=100), nullable=False),
        sa.Column("visual_style", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.String(length=30), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("stage_state", sa.JSON(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("continuity_rules", sa.JSON(), nullable=False),
        sa.Column("prop_locks", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drama_bibles_project_id", "drama_bibles", ["project_id"], unique=False)
    op.create_index(
        "ix_drama_bibles_project_updated",
        "drama_bibles",
        ["project_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "drama_characters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bible_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("appearance_lock", sa.Text(), nullable=False),
        sa.Column("wardrobe", sa.Text(), nullable=False),
        sa.Column("voice_id", sa.String(length=120), nullable=True),
        sa.Column("reference_asset_id", sa.String(length=36), nullable=True),
        sa.Column("prompt_anchor", sa.String(length=160), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["bible_id"], ["drama_bibles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reference_asset_id"], ["assets.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drama_characters_bible_id", "drama_characters", ["bible_id"], unique=False)
    op.create_index(
        "ix_drama_characters_bible_approval",
        "drama_characters",
        ["bible_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_locations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bible_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("visual_description", sa.Text(), nullable=False),
        sa.Column("reference_asset_ids", sa.JSON(), nullable=False),
        sa.Column("prompt_anchor", sa.String(length=160), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["bible_id"], ["drama_bibles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_drama_locations_bible_id", "drama_locations", ["bible_id"], unique=False)
    op.create_index(
        "ix_drama_locations_bible_approval",
        "drama_locations",
        ["bible_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_episodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bible_id", sa.String(length=36), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("synopsis", sa.Text(), nullable=False),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["bible_id"], ["drama_bibles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bible_id", "episode_number", name="uq_drama_episode_number"),
    )
    op.create_index("ix_drama_episodes_bible_id", "drama_episodes", ["bible_id"], unique=False)
    op.create_index(
        "ix_drama_episodes_bible_status",
        "drama_episodes",
        ["bible_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_scenes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("beat", sa.Text(), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("script_text", sa.Text(), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["episode_id"], ["drama_episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["location_id"], ["drama_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "sequence_index", name="uq_drama_scene_sequence"),
    )
    op.create_index("ix_drama_scenes_episode_id", "drama_scenes", ["episode_id"], unique=False)
    op.create_index(
        "ix_drama_scenes_episode_status",
        "drama_scenes",
        ["episode_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_shots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scene_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("character_ids", sa.JSON(), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=True),
        sa.Column("camera", sa.String(length=255), nullable=False),
        sa.Column("framing", sa.String(length=120), nullable=False),
        sa.Column("movement", sa.String(length=255), nullable=False),
        sa.Column("duration_hint", sa.Float(), nullable=False),
        sa.Column("visual_prompt", sa.Text(), nullable=False),
        sa.Column("prompt_anchor", sa.String(length=180), nullable=False),
        sa.Column("continuity_metadata", sa.JSON(), nullable=False),
        sa.Column("approval_status", sa.String(length=30), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["scene_id"], ["drama_scenes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["location_id"], ["drama_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "sequence_index", name="uq_drama_shot_sequence"),
    )
    op.create_index("ix_drama_shots_scene_id", "drama_shots", ["scene_id"], unique=False)
    op.create_index(
        "ix_drama_shots_scene_status",
        "drama_shots",
        ["scene_id", "approval_status"],
        unique=False,
    )

    op.create_table(
        "drama_dialogue_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("shot_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=True),
        sa.Column("speaker_name", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("delivery", sa.String(length=160), nullable=False),
        sa.Column("timing_hint", sa.String(length=120), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["shot_id"], ["drama_shots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["character_id"], ["drama_characters.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shot_id", "sequence_index", name="uq_drama_dialogue_sequence"),
    )
    op.create_index(
        "ix_drama_dialogue_lines_shot_id",
        "drama_dialogue_lines",
        ["shot_id"],
        unique=False,
    )

    with op.batch_alter_table("topic_proposals") as batch_op:
        batch_op.alter_column("content_brief", new_column_name="knowledge_brief")

    _canonicalize_data()


def downgrade() -> None:
    with op.batch_alter_table("topic_proposals") as batch_op:
        batch_op.alter_column("knowledge_brief", new_column_name="content_brief")

    op.drop_index("ix_drama_dialogue_lines_shot_id", table_name="drama_dialogue_lines")
    op.drop_table("drama_dialogue_lines")
    op.drop_index("ix_drama_shots_scene_status", table_name="drama_shots")
    op.drop_index("ix_drama_shots_scene_id", table_name="drama_shots")
    op.drop_table("drama_shots")
    op.drop_index("ix_drama_scenes_episode_status", table_name="drama_scenes")
    op.drop_index("ix_drama_scenes_episode_id", table_name="drama_scenes")
    op.drop_table("drama_scenes")
    op.drop_index("ix_drama_episodes_bible_status", table_name="drama_episodes")
    op.drop_index("ix_drama_episodes_bible_id", table_name="drama_episodes")
    op.drop_table("drama_episodes")
    op.drop_index("ix_drama_locations_bible_approval", table_name="drama_locations")
    op.drop_index("ix_drama_locations_bible_id", table_name="drama_locations")
    op.drop_table("drama_locations")
    op.drop_index("ix_drama_characters_bible_approval", table_name="drama_characters")
    op.drop_index("ix_drama_characters_bible_id", table_name="drama_characters")
    op.drop_table("drama_characters")
    op.drop_index("ix_drama_bibles_project_updated", table_name="drama_bibles")
    op.drop_index("ix_drama_bibles_project_id", table_name="drama_bibles")
    op.drop_table("drama_bibles")

    op.drop_index("ix_tasks_creative_plan_id", table_name="tasks")
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_tasks_creative_plan_id", type_="foreignkey")
        batch_op.drop_column("creative_plan_id")
    op.drop_index(
        "ix_commerce_creative_plans_product_id",
        table_name="commerce_creative_plans",
    )
    op.drop_table("commerce_creative_plans")

    op.drop_index("ix_tasks_product_id", table_name="tasks")
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_tasks_product_id", type_="foreignkey")
        batch_op.drop_column("creative_angle")
        batch_op.drop_column("product_id")
    op.drop_index("ix_product_assets_product_order", table_name="product_assets")
    op.drop_table("product_assets")
    op.drop_index("ix_products_updated_at", table_name="products")
    op.drop_table("products")

    with op.batch_alter_table("scenes", recreate="always") as batch_op:
        batch_op.drop_column("production_metadata")
        batch_op.drop_column("source_refs")
        batch_op.drop_column("claim_refs")
        batch_op.drop_column("visual_role")
    with op.batch_alter_table("tasks", recreate="always") as batch_op:
        batch_op.drop_column("production_mode")
    with op.batch_alter_table("projects", recreate="always") as batch_op:
        batch_op.drop_column("primary_production_mode")
