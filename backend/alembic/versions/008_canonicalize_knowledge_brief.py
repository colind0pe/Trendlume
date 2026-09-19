"""Make KnowledgeBrief the only persisted editorial brief contract."""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "008_canonicalize_knowledge_brief"
down_revision: str | None = "007_align_production_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(decoded) if isinstance(decoded, dict) else {}
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
            source.get("viewer_takeaway") or source.get("goal") or source.get("thesis") or ""
        ).strip()[:500],
        "key_claims": normalized_claims,
        "source_refs": list(dict.fromkeys(source_refs)),
        "genre": str(source.get("genre") or "auto").strip()[:100],
    }


def _rewrite_json_column(table_name: str, column_name: str, transform) -> None:
    bind = op.get_bind()
    table = sa.table(
        table_name,
        sa.column("id", sa.String(length=36)),
        sa.column(column_name, sa.JSON()),
    )
    rows = bind.execute(sa.select(table.c.id, table.c[column_name])).all()
    for row_id, raw_value in rows:
        current = _as_dict(raw_value)
        updated = transform(current)
        if updated != current:
            bind.execute(
                table.update()
                .where(table.c.id == row_id)
                .values(**{column_name: updated})
            )


def _normalize_payload(value: dict[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    legacy = payload.pop("content_brief", None)
    if "knowledge_brief" in payload:
        payload["knowledge_brief"] = _knowledge_brief(payload["knowledge_brief"])
    elif legacy is not None:
        payload["knowledge_brief"] = _knowledge_brief(legacy)
    return payload


def _normalize_settings(value: dict[str, Any]) -> dict[str, Any]:
    settings = dict(value)
    legacy = settings.pop("content_brief", None)
    if "knowledge_brief" in settings:
        settings["knowledge_brief"] = _knowledge_brief(settings["knowledge_brief"])
    elif legacy is not None:
        settings["knowledge_brief"] = _knowledge_brief(legacy)
    return settings


def upgrade() -> None:
    with op.batch_alter_table("topic_proposals") as batch_op:
        batch_op.alter_column("content_brief", new_column_name="knowledge_brief")

    _rewrite_json_column(
        "topic_proposals",
        "knowledge_brief",
        _knowledge_brief,
    )
    _rewrite_json_column("tasks", "input_payload", _normalize_payload)
    _rewrite_json_column("projects", "settings", _normalize_settings)


def downgrade() -> None:
    with op.batch_alter_table("topic_proposals") as batch_op:
        batch_op.alter_column("knowledge_brief", new_column_name="content_brief")
