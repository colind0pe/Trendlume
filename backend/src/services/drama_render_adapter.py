from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.exceptions import ValidationException
from src.domain.drama import ApprovalStatus
from src.models.drama import DramaBibleModel, DramaShotModel


@dataclass(frozen=True, slots=True)
class RenderSceneDraft:
    """The future hand-off shape for the existing render-segment pipeline."""

    source_shot_id: str
    sequence_index: int
    narration_text: str
    visual_prompt: str
    duration_seconds: float
    layout_params: dict[str, Any]
    production_metadata: dict[str, Any]


def adapt_approved_shots_to_render_scenes(
    bible: DramaBibleModel,
    *,
    episode_id: str | None = None,
) -> list[RenderSceneDraft]:
    """Adapt approved Drama shots without creating or generating SceneModel rows.

    This is deliberately a pure hand-off boundary. Callers may use the drafts
    in a later render task, but this phase refuses any unapproved media input.
    """

    if bible.approval_status != ApprovalStatus.APPROVED.value:
        raise ValidationException("Drama Storyboard 尚未批准，不能进入媒体生成。")

    drafts: list[RenderSceneDraft] = []
    sequence = 0
    for episode in bible.episodes:
        if episode_id and episode.id != episode_id:
            continue
        for scene in episode.scenes:
            for shot in scene.shots:
                if shot.approval_status != ApprovalStatus.APPROVED.value:
                    raise ValidationException(f"Shot {shot.id} 尚未批准，不能进入媒体生成。")
                sequence += 1
                drafts.append(_adapt_shot(bible, shot, sequence))
    if episode_id and not drafts:
        raise ValidationException(f"Drama Episode {episode_id} 不存在或没有可制作的 Shot。")
    return drafts


def _adapt_shot(bible: DramaBibleModel, shot: DramaShotModel, sequence: int) -> RenderSceneDraft:
    characters_by_id = {character.id: character for character in bible.characters}
    locations_by_id = {location.id: location for location in bible.locations}
    characters = [
        characters_by_id[character_id]
        for character_id in shot.character_ids or []
        if character_id in characters_by_id
    ]
    location = locations_by_id.get(shot.location_id or "")
    character_consistency = [
        {
            "id": character.id,
            "name": character.name,
            "canonical_description": character.description,
            "appearance_lock": character.appearance_lock,
            "wardrobe": character.wardrobe,
            "prompt_anchor": character.prompt_anchor,
            "reference_asset_id": character.reference_asset_id,
            "voice_id": character.voice_id,
        }
        for character in characters
    ]
    location_consistency = {
        "id": location.id if location else shot.location_id,
        "name": location.name if location else "",
        "visual_description": location.visual_description if location else "",
        "prompt_anchor": location.prompt_anchor if location else "",
        "reference_asset_ids": list(location.reference_asset_ids or []) if location else [],
    }
    character_prompt = "\n".join(
        "Character anchor: "
        f"{item['name']}; canonical description={item['canonical_description']}; "
        f"appearance={item['appearance_lock']}; wardrobe={item['wardrobe']}; "
        f"reference_asset_id={item['reference_asset_id'] or 'missing'}; "
        f"deterministic_anchor={item['prompt_anchor']}"
        for item in character_consistency
    )
    location_prompt = (
        "Location anchor: "
        f"{location_consistency['name']}; "
        f"description={location_consistency['visual_description']}; "
        f"reference_asset_ids={','.join(location_consistency['reference_asset_ids']) or 'none'}; "
        f"deterministic_anchor={location_consistency['prompt_anchor']}"
    )
    narration = shot.dialogue.strip() or shot.action.strip()
    anchor_line = f"Deterministic continuity anchor: {shot.prompt_anchor}."
    prompt_parts = [shot.visual_prompt.strip(), character_prompt, location_prompt]
    if bible.visual_style.strip():
        prompt_parts.insert(0, f"Visual style anchor: {bible.visual_style.strip()}")
    if shot.continuity_metadata:
        prompt_parts.insert(0, f"Continuity input: {shot.continuity_metadata}")
    return RenderSceneDraft(
        source_shot_id=shot.id,
        sequence_index=sequence,
        narration_text=narration,
        # Keep the original shot anchor as the final line for review and
        # deterministic continuity.
        visual_prompt="\n".join(part for part in prompt_parts if part).strip() + f"\n{anchor_line}",
        duration_seconds=shot.duration_hint,
        layout_params={
            "camera": shot.camera,
            "framing": shot.framing,
            "movement": shot.movement,
            "continuity_input": {
                "previous_shot_id": (shot.continuity_metadata or {}).get("previous_shot_id"),
                "last_frame_asset_id": (shot.continuity_metadata or {}).get("last_frame_asset_id"),
            },
            "dialogue_line_ids": [line.id for line in shot.dialogue_lines],
        },
        production_metadata={
            "source": "drama_shot",
            "source_shot_id": shot.id,
            "prompt_anchor": shot.prompt_anchor,
            "continuity": shot.continuity_metadata,
            "character_consistency": character_consistency,
            "location_consistency": location_consistency,
            "continuity_input": {
                "previous_shot_id": (shot.continuity_metadata or {}).get("previous_shot_id"),
                "last_frame_asset_id": (shot.continuity_metadata or {}).get("last_frame_asset_id"),
            },
            "dialogue_lines": [
                {
                    "id": line.id,
                    "sequence_index": line.sequence_index,
                    "character_id": line.character_id,
                    "speaker_name": line.speaker_name,
                    "text": line.text,
                    "delivery": line.delivery,
                    "timing_hint": line.timing_hint,
                }
                for line in shot.dialogue_lines
            ],
        },
    )
