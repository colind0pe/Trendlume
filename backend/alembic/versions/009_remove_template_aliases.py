"""Normalize persisted template aliases before removing runtime alias support."""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "009_remove_template_aliases"
down_revision: str | None = "008_canonicalize_knowledge_brief"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, dict) else {}


def upgrade() -> None:
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

    tasks = sa.table(
        "tasks",
        sa.column("id", sa.String(length=36)),
        sa.column("input_payload", sa.JSON()),
    )
    for task_id, raw_payload in bind.execute(
        sa.select(tasks.c.id, tasks.c.input_payload)
    ).all():
        payload = _as_dict(raw_payload)
        template_id = payload.get("template_id")
        normalized = TEMPLATE_ALIASES.get(template_id)
        if normalized:
            payload["template_id"] = normalized
            bind.execute(
                tasks.update()
                .where(tasks.c.id == task_id)
                .values(input_payload=payload)
            )


def downgrade() -> None:
    # Canonical IDs are intentionally not rewritten back to aliases. The
    # downgrade keeps the schema usable without reintroducing removed runtime
    # identifiers.
    pass
