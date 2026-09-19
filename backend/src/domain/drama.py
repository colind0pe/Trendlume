from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any


class DramaSourceType(StrEnum):
    IDEA = "idea"
    SCRIPT = "script"


class DramaStage(StrEnum):
    STORY = "story"
    BIBLE = "bible"
    ASSETS = "assets"
    EPISODE = "episode"
    STORYBOARD = "storyboard"
    APPROVAL = "approval"


class DramaWorkflowStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


DRAMA_STAGE_ORDER: tuple[DramaStage, ...] = (
    DramaStage.STORY,
    DramaStage.BIBLE,
    DramaStage.ASSETS,
    DramaStage.EPISODE,
    DramaStage.STORYBOARD,
    DramaStage.APPROVAL,
)


def initial_stage_state() -> dict[str, dict[str, Any]]:
    return {
        stage.value: {
            "status": "pending",
            "updated_at": None,
            "message": None,
        }
        for stage in DRAMA_STAGE_ORDER
    }


def _canonical_anchor_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _slug(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", value.strip().lower())
    return normalized.strip("-")[:40] or "entity"


def deterministic_prompt_anchor(kind: str, name: str, **locked_fields: Any) -> str:
    """Build a stable, provider-independent identity anchor for prompt reuse.

    The anchor is derived only from approved identity fields.  It deliberately
    contains no random seed and does not call a provider, so all shots that
    reference the same locked entity can reuse the same anchor.
    """

    payload = {"kind": kind, "name": name.strip(), **locked_fields}
    digest = hashlib.sha256(_canonical_anchor_payload(payload).encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{_slug(name)}:{digest}"


def character_prompt_anchor(
    name: str,
    appearance_lock: str,
    wardrobe: str,
    *,
    visual_style: str = "",
) -> str:
    return deterministic_prompt_anchor(
        "character",
        name,
        appearance_lock=appearance_lock.strip(),
        wardrobe=wardrobe.strip(),
        visual_style=visual_style.strip(),
    )


def location_prompt_anchor(
    name: str,
    visual_description: str,
    *,
    visual_style: str = "",
) -> str:
    return deterministic_prompt_anchor(
        "location",
        name,
        visual_description=visual_description.strip(),
        visual_style=visual_style.strip(),
    )


def shot_prompt_anchor(
    *,
    visual_style: str,
    location_anchor: str,
    character_anchors: list[str],
    camera: str,
    framing: str,
    movement: str,
    continuity_metadata: dict[str, Any] | None = None,
) -> str:
    return deterministic_prompt_anchor(
        "shot",
        "storyboard",
        visual_style=visual_style.strip(),
        location_anchor=location_anchor,
        character_anchors=sorted(character_anchors),
        camera=camera.strip(),
        framing=framing.strip(),
        movement=movement.strip(),
        continuity_metadata=continuity_metadata or {},
    )
