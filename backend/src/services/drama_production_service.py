from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.drama import (
    ApprovalStatus,
    DramaSourceType,
    DramaStage,
    DramaWorkflowStatus,
    character_prompt_anchor,
    initial_stage_state,
    location_prompt_anchor,
    shot_prompt_anchor,
)
from src.domain.enums import AssetType, JobType, ProductionMode, TaskStatus
from src.models.asset import AssetModel
from src.models.drama import (
    DramaBibleModel,
    DramaCharacterModel,
    DramaDialogueLineModel,
    DramaEpisodeModel,
    DramaLocationModel,
    DramaSceneModel,
    DramaShotModel,
)
from src.models.project import ProjectModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel, WorkflowStepRunModel
from src.schemas.drama import (
    DramaBibleCreate,
    DramaBibleUpdate,
    DramaCharacterUpdate,
    DramaEpisodeUpdate,
    DramaLocationUpdate,
    DramaPlanRequest,
    DramaProductionResponse,
    DramaProductionStartRequest,
    DramaSceneUpdate,
    DramaShotProductionResponse,
    DramaShotUpdate,
)
from src.services.drama_render_adapter import adapt_approved_shots_to_render_scenes
from src.services.provider_manager import ProviderManager
from src.services.template_catalog import template_catalog
from src.storage.local_storage import local_storage


def _now() -> datetime:
    return datetime.now(UTC)


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _key(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").strip().lower())


def _split_names(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,，、/；;]+", value) if item.strip()]


def _parse_duration(value: str | None) -> float:
    if not value:
        return 5.0
    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return 5.0
    return min(60.0, max(1.0, float(match.group(0))))


def _field_key(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "").replace("_", "")
    aliases = {
        "场景": "location",
        "地点": "location",
        "location": "location",
        "scene": "location",
        "角色": "characters",
        "人物": "characters",
        "characters": "characters",
        "character": "characters",
        "景别": "framing",
        "framing": "framing",
        "运镜": "movement",
        "镜头运动": "movement",
        "movement": "movement",
        "机位": "camera",
        "camera": "camera",
        "动作": "action",
        "action": "action",
        "画面": "visual_prompt",
        "视觉提示": "visual_prompt",
        "visual": "visual_prompt",
        "prompt": "visual_prompt",
        "台词": "dialogue",
        "对白": "dialogue",
        "dialogue": "dialogue",
        "时长": "duration",
        "duration": "duration",
        "连续性": "continuity",
        "continuity": "continuity",
        "道具": "props",
        "props": "props",
        "视线": "gaze",
        "gaze": "gaze",
    }
    return aliases.get(normalized, normalized)


def _parse_script(source_text: str, fallback_title: str) -> dict[str, Any]:
    """Parse a small human-friendly screenplay format without an LLM.

    The parser intentionally accepts the same lightweight shape used by the
    reference projects: headings, character bullets, and `key: value` shot
    fields. Unstructured paragraphs still produce a reviewable storyboard.
    """

    lines = [line.rstrip() for line in source_text.splitlines()]
    title = fallback_title
    genre = ""
    character_specs: list[dict[str, str]] = []
    blocks: list[dict[str, str]] = []
    section = ""
    current: dict[str, str] | None = None

    def finish_block() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        title_match = re.match(r"^#\s*(?:标题|title)\s*[:：]\s*(.+)$", line, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            continue
        genre_match = re.match(r"^#\s*(?:题材|genre)\s*[:：]\s*(.+)$", line, re.IGNORECASE)
        if genre_match:
            genre = genre_match.group(1).strip()
            continue

        if line.startswith("###"):
            finish_block()
            section = "shots"
            current = {"label": re.sub(r"^###+\s*", "", line).strip()}
            continue
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            finish_block()
            heading = heading_match.group(1).strip().lower()
            if any(token in heading for token in ("角色", "人物", "character")):
                section = "characters"
            elif any(token in heading for token in ("分镜", "镜头", "shot", "storyboard")):
                section = "shots"
            else:
                section = "other"
            continue

        if section == "characters" and line[:1] in {"-", "*"}:
            raw_character = line[1:].strip()
            parts = [part.strip() for part in raw_character.split("|")]
            if parts and parts[0]:
                character_specs.append(
                    {
                        "name": parts[0],
                        "description": parts[1] if len(parts) > 1 else "",
                        "appearance_lock": parts[2] if len(parts) > 2 else "",
                        "wardrobe": parts[3] if len(parts) > 3 else "",
                    }
                )
            continue

        field_match = re.match(r"^([^:：]{1,24})\s*[:：]\s*(.*)$", line)
        if field_match:
            if current is None:
                current = {"label": f"镜头 {len(blocks) + 1}"}
            raw_key = field_match.group(1).strip()
            key = _field_key(raw_key)
            value = field_match.group(2).strip()
            # Screenplays commonly put the next speaker on its own line, for
            # example `旁白：...` after `台词：林夏：...`. Preserve that line
            # as another DialogueLine instead of treating the speaker as an
            # unknown shot field. Character names are known by this point
            # because the character section precedes the shot section.
            if section == "shots" and key not in {
                "location",
                "characters",
                "framing",
                "movement",
                "camera",
                "action",
                "visual_prompt",
                "dialogue",
                "duration",
                "continuity",
                "props",
                "gaze",
            } and (
                _key(raw_key) in {_key(item["name"]) for item in character_specs}
                or _key(raw_key) in {"旁白", "narration", "voiceover"}
            ):
                key = "dialogue"
                value = f"{raw_key}:{value}"
            if key == "dialogue" and current.get(key):
                # Multiple DialogueLine declarations in one Shot are valid;
                # retain their order for the later line-level TTS stage.
                current[key] = f"{current[key]}\n{value}"
            else:
                current[key] = value
            if section == "shots":
                continue

        if section == "shots":
            if current is None:
                current = {"label": f"镜头 {len(blocks) + 1}"}
            current["action"] = f"{current.get('action', '')} {line}".strip()

    finish_block()

    if not blocks:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", source_text) if part.strip()]
        blocks = [
            {
                "label": f"镜头 {index + 1}",
                "location": "主要场景",
                "action": paragraph,
                "visual_prompt": paragraph,
            }
            for index, paragraph in enumerate(paragraphs or [source_text.strip()])
        ]

    for block in blocks:
        block.setdefault("location", "主要场景")
        block.setdefault("action", block.get("visual_prompt") or block.get("dialogue") or "推进剧情")
        block.setdefault("visual_prompt", block.get("action", ""))
        block.setdefault("camera", "固定机位")
        block.setdefault("framing", "中景")
        block.setdefault("movement", "固定")
        block.setdefault("duration", "5 秒")
        block.setdefault("characters", "")

    if not title.strip():
        title = fallback_title
    return {
        "title": title[:255],
        "genre": genre,
        "characters": character_specs,
        "blocks": blocks,
    }


def _idea_plan(bible: DramaBibleModel) -> dict[str, Any]:
    idea = bible.source_text.strip()
    return {
        "title": bible.title,
        "genre": bible.genre,
        "characters": [
            {
                "name": "主角",
                "description": f"围绕「{idea[:160]}」行动的核心人物，动机和关系待确认。",
                "appearance_lock": "待确认：年龄、脸型、肤色、发型与一项可识别特征。",
                "wardrobe": "待确认：本集稳定造型、颜色和关键配饰。",
            }
        ],
        "blocks": [
            {
                "label": "开场",
                "location": "主要场景",
                "characters": "主角",
                "action": idea,
                "visual_prompt": f"{bible.visual_style}；把故事想法「{idea[:240]}」转成可拍的开场画面。",
                "camera": "固定机位",
                "framing": "中景",
                "movement": "缓慢推进",
                "duration": "5 秒",
                "dialogue": "",
            }
        ],
    }


class DramaProductionService:
    """Owns Drama pre-production and its approval gates.

    This service creates structured text and metadata only. It does not call an
    image, video, audio, or rendering Provider.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_bible(self, project_id: str, payload: DramaBibleCreate) -> DramaBibleModel:
        project = await self.session.get(ProjectModel, project_id)
        if not project:
            raise NotFoundException("Project", project_id)

        bible = DramaBibleModel(
            id=_make_id("drama"),
            project_id=project_id,
            source_type=payload.source_type.value,
            source_text=payload.source_text.strip(),
            title=payload.title.strip(),
            logline=(payload.logline.strip() or payload.source_text.strip()[:500]),
            genre=payload.genre.strip(),
            tone=payload.tone.strip(),
            visual_style=payload.visual_style.strip(),
            stage_state=initial_stage_state(),
            checkpoint={"last_completed_stage": None, "resume_stage": DramaStage.STORY.value},
            continuity_rules=payload.continuity_rules,
            prop_locks=payload.prop_locks,
        )
        self.session.add(bible)
        await self.session.flush()
        return bible

    async def list_bibles(self, project_id: str) -> list[DramaBibleModel]:
        result = await self.session.execute(
            select(DramaBibleModel)
            .where(DramaBibleModel.project_id == project_id)
            .order_by(DramaBibleModel.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_bible(self, drama_id: str) -> DramaBibleModel:
        bible = await self.session.get(DramaBibleModel, drama_id)
        if not bible:
            raise NotFoundException("DramaBible", drama_id)
        return bible

    async def get_detail(self, drama_id: str) -> DramaBibleModel:
        result = await self.session.execute(
            select(DramaBibleModel)
            .where(DramaBibleModel.id == drama_id)
            .options(
                selectinload(DramaBibleModel.characters),
                selectinload(DramaBibleModel.locations),
                selectinload(DramaBibleModel.episodes)
                .selectinload(DramaEpisodeModel.scenes)
                .selectinload(DramaSceneModel.shots)
                .selectinload(DramaShotModel.dialogue_lines),
            )
        )
        bible = result.scalar_one_or_none()
        if not bible:
            raise NotFoundException("DramaBible", drama_id)
        return bible

    async def update_bible(self, drama_id: str, payload: DramaBibleUpdate) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        changes = payload.model_dump(exclude_unset=True)
        visual_style_changed = changes.get("visual_style") is not None and changes["visual_style"] != bible.visual_style
        for field, value in changes.items():
            setattr(bible, field, value.strip() if isinstance(value, str) else value)
        if changes:
            bible.revision += 1
            if visual_style_changed:
                await self._mark_assets_for_review(bible)
                await self._refresh_shot_anchors(bible.id)
            bible.current_stage = DramaStage.APPROVAL.value
            bible.workflow_status = DramaWorkflowStatus.PAUSED.value
            self._set_stage(bible, DramaStage.APPROVAL, "awaiting_approval", "Bible 修改后需要重新确认")
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def plan(self, drama_id: str, payload: DramaPlanRequest) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        existing = await self.session.scalar(
            select(DramaEpisodeModel.id).where(DramaEpisodeModel.bible_id == bible.id).limit(1)
        )
        if existing:
            if payload.regenerate:
                raise ValidationException("已有分集规划，当前阶段请先编辑或新建 Drama Bible，不覆盖已审阅内容。")
            raise ValidationException("该 Drama Bible 已完成结构化规划。")

        plan = _parse_script(bible.source_text, bible.title) if bible.source_type == DramaSourceType.SCRIPT.value else _idea_plan(bible)
        if plan.get("genre") and not bible.genre:
            bible.genre = plan["genre"]
        await self._build_plan(bible, plan)
        self._set_stage(bible, DramaStage.STORY, "completed", "故事输入已登记")
        self._set_stage(bible, DramaStage.BIBLE, "completed", "Bible 草案已建立")
        self._set_stage(bible, DramaStage.ASSETS, "awaiting_approval", "角色与场景等待人工确认")
        self._set_stage(bible, DramaStage.EPISODE, "awaiting_approval", "单集剧本等待人工确认")
        self._set_stage(bible, DramaStage.STORYBOARD, "awaiting_approval", "逐 Shot Storyboard 等待人工确认")
        self._set_stage(bible, DramaStage.APPROVAL, "pending", "确认后才允许进入后续制作")
        bible.current_stage = DramaStage.APPROVAL.value
        bible.workflow_status = DramaWorkflowStatus.PAUSED.value
        bible.approval_status = ApprovalStatus.IN_REVIEW.value
        bible.checkpoint = {
            "last_completed_stage": DramaStage.BIBLE.value,
            "resume_stage": DramaStage.ASSETS.value,
            "reason": "awaiting_manual_approval",
            "updated_at": _now().isoformat(),
        }
        bible.revision += 1
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def _build_plan(self, bible: DramaBibleModel, plan: dict[str, Any]) -> None:
        characters: dict[str, DramaCharacterModel] = {}
        for spec in plan["characters"]:
            name = str(spec.get("name") or "未命名角色").strip()
            character = DramaCharacterModel(
                id=_make_id("character"),
                bible_id=bible.id,
                name=name,
                description=str(spec.get("description") or "从输入材料提取，待确认。"),
                appearance_lock=str(
                    spec.get("appearance_lock") or "待确认：脸型、肤色、发型、体态与标志性特征。"
                ),
                wardrobe=str(spec.get("wardrobe") or "待确认：造型阶段、颜色和关键配饰。"),
                prompt_anchor=character_prompt_anchor(
                    name,
                    str(spec.get("appearance_lock") or "待确认"),
                    str(spec.get("wardrobe") or "待确认"),
                    visual_style=bible.visual_style,
                ),
                continuity_metadata={"source": "script" if bible.source_type == "script" else "idea"},
            )
            self.session.add(character)
            characters[_key(name)] = character

        locations: dict[str, DramaLocationModel] = {}
        for block in plan["blocks"]:
            name = str(block.get("location") or "主要场景").strip()
            if _key(name) in locations:
                continue
            description = str(
                block.get("location_description")
                or f"{name}；空间布局、材质、时间与光线待确认。"
            )
            location = DramaLocationModel(
                id=_make_id("location"),
                bible_id=bible.id,
                name=name,
                visual_description=description,
                prompt_anchor=location_prompt_anchor(
                    name, description, visual_style=bible.visual_style
                ),
                continuity_metadata={
                    "time_of_day": block.get("time_of_day", "待确认"),
                    "spatial_rule": block.get("continuity", "保持空间坐标稳定"),
                },
            )
            self.session.add(location)
            locations[_key(name)] = location

        episode = DramaEpisodeModel(
            id=_make_id("episode"),
            bible_id=bible.id,
            episode_number=1,
            title=f"第一集 · {plan['title'][:180]}",
            synopsis=bible.logline or bible.source_text[:500],
            script_text=bible.source_text,
            continuity_metadata={
                "rules": bible.continuity_rules,
                "prop_locks": bible.prop_locks,
                "checkpoint": "episode_1",
            },
            checkpoint={"source_type": bible.source_type, "parsed_shots": len(plan["blocks"])},
        )
        self.session.add(episode)

        scene_models: list[DramaSceneModel] = []
        previous_location_key = ""
        previous_shot: DramaShotModel | None = None
        current_scene_shot_index = 0
        for shot_index, block in enumerate(plan["blocks"], start=1):
            location_name = str(block.get("location") or "主要场景").strip()
            location = locations[_key(location_name)]
            new_scene = not scene_models or previous_location_key != _key(location_name)
            if new_scene:
                scene = DramaSceneModel(
                    id=_make_id("scene"),
                    episode_id=episode.id,
                    sequence_index=len(scene_models) + 1,
                    title=f"场景 {len(scene_models) + 1} · {location_name}",
                    summary=str(block.get("action") or block.get("visual_prompt") or "推进剧情"),
                    beat=str(block.get("label") or "剧情推进"),
                    location_id=location.id,
                    script_text=str(block.get("action") or ""),
                    continuity_metadata={"location_anchor": location.prompt_anchor},
                )
                self.session.add(scene)
                scene_models.append(scene)
                previous_location_key = _key(location_name)
                current_scene_shot_index = 0
            scene = scene_models[-1]
            current_scene_shot_index += 1

            names = _split_names(block.get("characters"))
            character_ids: list[str] = []
            for name in names:
                character = characters.get(_key(name))
                if not character:
                    character = DramaCharacterModel(
                        id=_make_id("character"),
                        bible_id=bible.id,
                        name=name,
                        description="从镜头字段提取，待补充人物动机。",
                        appearance_lock="待确认：脸型、肤色、发型、体态与标志性特征。",
                        wardrobe="待确认：造型阶段、颜色和关键配饰。",
                        prompt_anchor=character_prompt_anchor(
                            name,
                            "待确认",
                            "待确认",
                            visual_style=bible.visual_style,
                        ),
                        continuity_metadata={"source": "shot_field"},
                    )
                    self.session.add(character)
                    characters[_key(name)] = character
                if character.id not in character_ids:
                    character_ids.append(character.id)

            dialogue = str(block.get("dialogue") or "")
            continuity = {
                "previous_shot_id": previous_shot.id if previous_shot else None,
                "props": block.get("props", ""),
                "gaze": block.get("gaze", ""),
                "rule": block.get("continuity", ""),
            }
            anchors = [characters[_key(name)].prompt_anchor for name in names if _key(name) in characters]
            shot = DramaShotModel(
                id=_make_id("shot"),
                scene_id=scene.id,
                sequence_index=current_scene_shot_index,
                action=str(block.get("action") or "推进剧情"),
                dialogue=dialogue,
                character_ids=character_ids,
                location_id=location.id,
                camera=str(block.get("camera") or "固定机位"),
                framing=str(block.get("framing") or "中景"),
                movement=str(block.get("movement") or "固定"),
                duration_hint=_parse_duration(block.get("duration")),
                visual_prompt=str(block.get("visual_prompt") or block.get("action") or ""),
                prompt_anchor=shot_prompt_anchor(
                    visual_style=bible.visual_style,
                    location_anchor=location.prompt_anchor,
                    character_anchors=anchors,
                    camera=str(block.get("camera") or "固定机位"),
                    framing=str(block.get("framing") or "中景"),
                    movement=str(block.get("movement") or "固定"),
                    continuity_metadata=continuity,
                ),
                continuity_metadata=continuity,
            )
            self.session.add(shot)
            self._add_dialogue_lines(shot, dialogue, characters)
            previous_shot = shot

    def _add_dialogue_lines(
        self,
        shot: DramaShotModel,
        dialogue: str,
        characters: dict[str, DramaCharacterModel],
    ) -> None:
        if not dialogue.strip():
            return
        lines = [line.strip() for line in re.split(r"\n+", dialogue) if line.strip()]
        for index, line in enumerate(lines, start=1):
            speaker = "旁白"
            text = line
            match = re.match(r"^([^:：]{1,40})\s*[:：]\s*(.+)$", line)
            if match:
                speaker, text = match.group(1).strip(), match.group(2).strip()
            character = characters.get(_key(speaker))
            self.session.add(
                DramaDialogueLineModel(
                    id=_make_id("dialogue"),
                    shot_id=shot.id,
                    sequence_index=index,
                    character_id=character.id if character else None,
                    speaker_name=speaker,
                    text=text,
                )
            )

    def _set_stage(
        self,
        bible: DramaBibleModel,
        stage: DramaStage,
        status: str,
        message: str,
    ) -> None:
        state = dict(bible.stage_state or initial_stage_state())
        state[stage.value] = {
            "status": status,
            "updated_at": _now().isoformat(),
            "message": message,
        }
        bible.stage_state = state

    async def _mark_assets_for_review(self, bible: DramaBibleModel) -> None:
        detail = await self.get_detail(bible.id)
        for entity in [*detail.characters, *detail.locations]:
            if entity.approval_status == ApprovalStatus.APPROVED.value:
                entity.approval_status = ApprovalStatus.CHANGES_REQUESTED.value
                entity.approved_at = None
        for episode in detail.episodes:
            for scene in episode.scenes:
                for shot in scene.shots:
                    if shot.approval_status == ApprovalStatus.APPROVED.value:
                        shot.approval_status = ApprovalStatus.CHANGES_REQUESTED.value
                        shot.approved_at = None
                if scene.approval_status == ApprovalStatus.APPROVED.value:
                    scene.approval_status = ApprovalStatus.CHANGES_REQUESTED.value
                    scene.approved_at = None
            if episode.approval_status == ApprovalStatus.APPROVED.value:
                episode.approval_status = ApprovalStatus.CHANGES_REQUESTED.value
                episode.approved_at = None
        bible.approval_status = ApprovalStatus.IN_REVIEW.value

    async def update_character(
        self, drama_id: str, character_id: str, payload: DramaCharacterUpdate
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        character = await self._get_character(bible.id, character_id)
        changes = payload.model_dump(exclude_unset=True)
        if "reference_asset_id" in changes and changes["reference_asset_id"]:
            asset = await self.session.get(AssetModel, changes["reference_asset_id"])
            if not asset or asset.project_id != bible.project_id:
                raise ValidationException("角色参考资产不存在或不属于当前项目。")
        for field, value in changes.items():
            setattr(character, field, value.strip() if isinstance(value, str) else value)
        character.prompt_anchor = character_prompt_anchor(
            character.name,
            character.appearance_lock,
            character.wardrobe,
            visual_style=bible.visual_style,
        )
        self._mark_changed(character)
        await self._refresh_shot_anchors(bible.id)
        await self._update_asset_stage(bible)
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def update_location(
        self, drama_id: str, location_id: str, payload: DramaLocationUpdate
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        location = await self._get_location(bible.id, location_id)
        changes = payload.model_dump(exclude_unset=True)
        reference_asset_ids = changes.get("reference_asset_ids")
        if reference_asset_ids:
            result = await self.session.execute(
                select(AssetModel.id).where(
                    AssetModel.project_id == bible.project_id,
                    AssetModel.id.in_(reference_asset_ids),
                )
            )
            found = {row[0] for row in result.all()}
            missing = [asset_id for asset_id in reference_asset_ids if asset_id not in found]
            if missing:
                raise ValidationException("场景参考资产不存在或不属于当前项目。")
        for field, value in changes.items():
            setattr(location, field, value.strip() if isinstance(value, str) else value)
        location.prompt_anchor = location_prompt_anchor(
            location.name, location.visual_description, visual_style=bible.visual_style
        )
        self._mark_changed(location)
        await self._refresh_shot_anchors(bible.id)
        await self._update_asset_stage(bible)
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def update_episode(
        self, drama_id: str, episode_id: str, payload: DramaEpisodeUpdate
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        episode = await self._get_episode(bible.id, episode_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(episode, field, value.strip() if isinstance(value, str) else value)
        self._mark_changed(episode)
        for scene in episode.scenes:
            self._mark_changed(scene)
            for shot in scene.shots:
                self._mark_changed(shot)
        bible.approval_status = ApprovalStatus.IN_REVIEW.value
        bible.current_stage = DramaStage.EPISODE.value
        self._set_stage(bible, DramaStage.EPISODE, "awaiting_approval", "单集剧本修改后需要重新确认")
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def update_scene(
        self, drama_id: str, scene_id: str, payload: DramaSceneUpdate
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        scene = await self._get_scene(bible.id, scene_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("location_id"):
            await self._get_location(bible.id, changes["location_id"])
        for field, value in changes.items():
            setattr(scene, field, value.strip() if isinstance(value, str) else value)
        self._mark_changed(scene)
        for shot in scene.shots:
            self._mark_changed(shot)
        bible.approval_status = ApprovalStatus.IN_REVIEW.value
        bible.current_stage = DramaStage.EPISODE.value
        self._set_stage(bible, DramaStage.EPISODE, "awaiting_approval", "场次修改后需要重新确认单集剧本")
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def update_shot(self, drama_id: str, shot_id: str, payload: DramaShotUpdate) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        shot = await self._get_shot(bible.id, shot_id)
        changes = payload.model_dump(exclude_unset=True)
        if "character_ids" in changes:
            await self._validate_character_ids(bible.id, changes["character_ids"] or [])
        if changes.get("location_id"):
            await self._get_location(bible.id, changes["location_id"])
        for field, value in changes.items():
            setattr(shot, field, value.strip() if isinstance(value, str) else value)
        await self._refresh_one_shot_anchor(bible, shot)
        self._mark_changed(shot)
        bible.approval_status = ApprovalStatus.IN_REVIEW.value
        bible.current_stage = DramaStage.STORYBOARD.value
        self._set_stage(bible, DramaStage.STORYBOARD, "awaiting_approval", "Shot 修改后需要重新确认")
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def approve_character(
        self, drama_id: str, character_id: str, note: str | None = None
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        character = await self._get_character(bible.id, character_id)
        if not character.name.strip() or not character.appearance_lock.strip() or not character.wardrobe.strip():
            raise ValidationException("角色还缺少姓名、外观锁或服装锁，补齐后才能确认。")
        self._approve(character, note)
        await self._refresh_shot_anchors(bible.id)
        await self._update_asset_stage(bible)
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def approve_location(
        self, drama_id: str, location_id: str, note: str | None = None
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        location = await self._get_location(bible.id, location_id)
        if not location.name.strip() or not location.visual_description.strip():
            raise ValidationException("场景还缺少名称或稳定视觉描述，补齐后才能确认。")
        self._approve(location, note)
        await self._refresh_shot_anchors(bible.id)
        await self._update_asset_stage(bible)
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def approve_shot(
        self, drama_id: str, shot_id: str, note: str | None = None
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        shot = await self._get_shot(bible.id, shot_id)
        scene = await self.session.get(DramaSceneModel, shot.scene_id)
        episode = await self.session.get(DramaEpisodeModel, scene.episode_id) if scene else None
        if not episode or episode.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("请先确认单集剧本，再确认 Shot。")
        if not scene or scene.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("请先确认当前场景，再确认 Shot。")
        await self._validate_shot_for_approval(bible, shot)
        self._approve(shot, note)
        bible.current_stage = DramaStage.STORYBOARD.value
        self._set_stage(bible, DramaStage.STORYBOARD, "awaiting_approval", "逐 Shot Storyboard 等待确认")
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def approve_scene(
        self, drama_id: str, scene_id: str, note: str | None = None
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        scene = await self._get_scene(bible.id, scene_id)
        episode = await self.session.get(DramaEpisodeModel, scene.episode_id)
        if not episode or episode.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("请先确认单集剧本，再确认场景。")
        if not scene.title.strip() or not scene.summary.strip() or not scene.location_id:
            raise ValidationException("场景需要标题、摘要和场景绑定后才能确认。")
        location = await self._get_location(bible.id, scene.location_id)
        if location.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("场景所绑定的视觉场景尚未确认。")
        self._approve(scene, note)
        bible.current_stage = DramaStage.STORYBOARD.value
        self._set_stage(bible, DramaStage.STORYBOARD, "awaiting_approval", "场景已确认，逐 Shot Storyboard 等待确认")
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def approve_episode(
        self, drama_id: str, episode_id: str, note: str | None = None
    ) -> DramaBibleModel:
        bible = await self.get_bible(drama_id)
        episode = await self._get_episode(bible.id, episode_id)
        detail = await self.get_detail(bible.id)
        if not detail.characters or not detail.locations or any(
            entity.approval_status != ApprovalStatus.APPROVED.value
            for entity in [*detail.characters, *detail.locations]
        ):
            raise ValidationException("请先确认全部角色和视觉场景，再确认单集剧本。")
        if not episode.title.strip() or not episode.script_text.strip() or not episode.scenes:
            raise ValidationException("单集需要标题、剧本原文和至少一个场景后才能确认。")
        if any(not scene.title.strip() or not scene.summary.strip() or not scene.location_id for scene in episode.scenes):
            raise ValidationException("单集中的每个场景都需要标题、摘要和场景绑定。")
        self._approve(episode, note)
        episode.workflow_status = DramaWorkflowStatus.COMPLETED.value
        bible.approval_status = ApprovalStatus.IN_REVIEW.value
        bible.current_stage = DramaStage.STORYBOARD.value
        self._set_stage(bible, DramaStage.EPISODE, "completed", "单集剧本已确认")
        self._set_stage(bible, DramaStage.STORYBOARD, "awaiting_approval", "场景确认后进入逐 Shot Storyboard")
        bible.checkpoint = {
            **(bible.checkpoint or {}),
            "last_completed_stage": DramaStage.EPISODE.value,
            "resume_stage": DramaStage.STORYBOARD.value,
            "reason": "episode_approved",
            "updated_at": _now().isoformat(),
        }
        await self.session.flush()
        return await self.get_detail(drama_id)

    async def storyboard_preflight(self, drama_id: str) -> dict[str, Any]:
        bible = await self.get_detail(drama_id)
        characters = list(bible.characters)
        locations = list(bible.locations)
        shots = [shot for episode in bible.episodes for scene in episode.scenes for shot in scene.shots]
        checks: list[dict[str, Any]] = []

        assets_ready = bool(characters) and bool(locations) and all(
            item.approval_status == ApprovalStatus.APPROVED.value for item in [*characters, *locations]
        )
        checks.append(
            {
                "key": "assets_approved",
                "label": "角色与场景已确认",
                "passed": assets_ready,
                "message": "所有角色和场景需要先确认。" if not assets_ready else "角色与场景确认完成。",
            }
        )
        episodes_ready = bool(bible.episodes) and all(
            episode.approval_status == ApprovalStatus.APPROVED.value for episode in bible.episodes
        )
        checks.append(
            {
                "key": "episode_approved",
                "label": "单集剧本已确认",
                "passed": episodes_ready,
                "message": "先确认单集剧本。" if not episodes_ready else "单集剧本确认完成。",
            }
        )
        scenes = [scene for episode in bible.episodes for scene in episode.scenes]
        scenes_ready = bool(scenes) and all(
            scene.approval_status == ApprovalStatus.APPROVED.value for scene in scenes
        )
        checks.append(
            {
                "key": "scenes_approved",
                "label": "场景结构已确认",
                "passed": scenes_ready,
                "message": "先确认每个场景结构。" if not scenes_ready else "场景结构确认完成。",
            }
        )
        complete_shots = bool(shots) and all(
            shot.action.strip()
            and shot.visual_prompt.strip()
            and shot.location_id
            and shot.duration_hint > 0
            for shot in shots
        )
        checks.append(
            {
                "key": "shots_complete",
                "label": "Shot 信息完整",
                "passed": complete_shots,
                "message": "每个 Shot 需要动作、场景、时长和视觉提示。" if not complete_shots else "Shot 字段完整。",
            }
        )
        shots_approved = bool(shots) and all(
            shot.approval_status == ApprovalStatus.APPROVED.value for shot in shots
        )
        checks.append(
            {
                "key": "shots_approved",
                "label": "逐 Shot 已确认",
                "passed": shots_approved,
                "message": "逐个确认 Storyboard Shot 后才能进入最终批准。" if not shots_approved else "Storyboard Shot 全部确认。",
            }
        )
        return {
            "drama_id": bible.id,
            "ready": all(check["passed"] for check in checks),
            "blocking": not all(check["passed"] for check in checks),
            "current_stage": bible.current_stage,
            "checks": checks,
        }

    async def approve_storyboard(
        self, drama_id: str, note: str | None = None
    ) -> tuple[DramaBibleModel, dict[str, Any]]:
        bible = await self.get_bible(drama_id)
        preflight = await self.storyboard_preflight(drama_id)
        if not preflight["ready"]:
            failed = [check["message"] for check in preflight["checks"] if not check["passed"]]
            raise ValidationException("无法批准 Storyboard：" + "；".join(failed))

        bible.approval_status = ApprovalStatus.APPROVED.value
        bible.workflow_status = DramaWorkflowStatus.COMPLETED.value
        bible.current_stage = DramaStage.APPROVAL.value
        self._set_stage(bible, DramaStage.ASSETS, "completed", "角色与场景已确认")
        self._set_stage(bible, DramaStage.EPISODE, "completed", "单集剧本已确认")
        self._set_stage(bible, DramaStage.STORYBOARD, "completed", "逐 Shot Storyboard 已确认")
        self._set_stage(bible, DramaStage.APPROVAL, "completed", "已批准进入后续制作")
        bible.checkpoint = {
            "last_completed_stage": DramaStage.APPROVAL.value,
            "resume_stage": None,
            "reason": "approved_storyboard",
            "updated_at": _now().isoformat(),
        }
        bible.revision += 1
        await self.session.flush()
        return await self.get_detail(drama_id), await self.storyboard_preflight(drama_id)

    async def _get_character(self, bible_id: str, character_id: str) -> DramaCharacterModel:
        entity = await self.session.scalar(
            select(DramaCharacterModel).where(
                DramaCharacterModel.id == character_id,
                DramaCharacterModel.bible_id == bible_id,
            )
        )
        if not entity:
            raise NotFoundException("Drama Character", character_id)
        return entity

    async def _get_location(self, bible_id: str, location_id: str) -> DramaLocationModel:
        entity = await self.session.scalar(
            select(DramaLocationModel).where(
                DramaLocationModel.id == location_id,
                DramaLocationModel.bible_id == bible_id,
            )
        )
        if not entity:
            raise NotFoundException("Drama Location", location_id)
        return entity

    async def _get_episode(self, bible_id: str, episode_id: str) -> DramaEpisodeModel:
        entity = await self.session.scalar(
            select(DramaEpisodeModel).where(
                DramaEpisodeModel.id == episode_id,
                DramaEpisodeModel.bible_id == bible_id,
            ).options(selectinload(DramaEpisodeModel.scenes).selectinload(DramaSceneModel.shots))
        )
        if not entity:
            raise NotFoundException("Drama Episode", episode_id)
        return entity

    async def _get_scene(self, bible_id: str, scene_id: str) -> DramaSceneModel:
        entity = await self.session.scalar(
            select(DramaSceneModel)
            .join(DramaEpisodeModel)
            .where(DramaSceneModel.id == scene_id, DramaEpisodeModel.bible_id == bible_id)
            .options(selectinload(DramaSceneModel.shots))
        )
        if not entity:
            raise NotFoundException("Drama Scene", scene_id)
        return entity

    async def _get_shot(self, bible_id: str, shot_id: str) -> DramaShotModel:
        entity = await self.session.scalar(
            select(DramaShotModel)
            .join(DramaSceneModel)
            .join(DramaEpisodeModel)
            .where(DramaShotModel.id == shot_id, DramaEpisodeModel.bible_id == bible_id)
        )
        if not entity:
            raise NotFoundException("Drama Shot", shot_id)
        return entity

    async def _validate_character_ids(self, bible_id: str, character_ids: list[str]) -> None:
        if not character_ids:
            return
        result = await self.session.execute(
            select(DramaCharacterModel.id).where(
                DramaCharacterModel.bible_id == bible_id,
                DramaCharacterModel.id.in_(character_ids),
            )
        )
        found = {row[0] for row in result.all()}
        missing = [character_id for character_id in character_ids if character_id not in found]
        if missing:
            raise ValidationException("Shot 引用了不属于当前 Drama Bible 的角色。")

    async def _validate_shot_for_approval(self, bible: DramaBibleModel, shot: DramaShotModel) -> None:
        if not shot.action.strip() or not shot.visual_prompt.strip() or shot.duration_hint <= 0:
            raise ValidationException("Shot 需要动作、视觉提示和有效时长。")
        if not shot.location_id:
            raise ValidationException("Shot 必须绑定场景后才能确认。")
        location = await self._get_location(bible.id, shot.location_id)
        if location.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("Shot 所绑定的场景尚未确认。")
        await self._validate_character_ids(bible.id, shot.character_ids or [])
        if shot.character_ids:
            result = await self.session.execute(
                select(DramaCharacterModel.approval_status).where(
                    DramaCharacterModel.id.in_(shot.character_ids),
                    DramaCharacterModel.bible_id == bible.id,
                )
            )
            if any(row[0] != ApprovalStatus.APPROVED.value for row in result.all()):
                raise ValidationException("Shot 所绑定的角色尚未全部确认。")

    async def _refresh_shot_anchors(self, bible_id: str) -> None:
        result = await self.session.execute(
            select(DramaShotModel)
            .join(DramaSceneModel)
            .join(DramaEpisodeModel)
            .where(DramaEpisodeModel.bible_id == bible_id)
        )
        bible = await self.get_bible(bible_id)
        for shot in result.scalars().all():
            await self._refresh_one_shot_anchor(bible, shot)

    async def _refresh_one_shot_anchor(self, bible: DramaBibleModel, shot: DramaShotModel) -> None:
        location = await self.session.get(DramaLocationModel, shot.location_id) if shot.location_id else None
        result = await self.session.execute(
            select(DramaCharacterModel).where(
                DramaCharacterModel.bible_id == bible.id,
                DramaCharacterModel.id.in_(shot.character_ids or []),
            )
        ) if shot.character_ids else None
        characters = list(result.scalars().all()) if result else []
        shot.prompt_anchor = shot_prompt_anchor(
            visual_style=bible.visual_style,
            location_anchor=location.prompt_anchor if location else "",
            character_anchors=[character.prompt_anchor for character in characters],
            camera=shot.camera,
            framing=shot.framing,
            movement=shot.movement,
            continuity_metadata=shot.continuity_metadata,
        )

    async def _update_asset_stage(self, bible: DramaBibleModel) -> None:
        detail = await self.get_detail(bible.id)
        entities = [*detail.characters, *detail.locations]
        if entities and all(entity.approval_status == ApprovalStatus.APPROVED.value for entity in entities):
            self._set_stage(bible, DramaStage.ASSETS, "completed", "角色与场景已确认")
            bible.current_stage = DramaStage.EPISODE.value
            self._set_stage(bible, DramaStage.EPISODE, "awaiting_approval", "单集剧本等待人工确认")
            bible.checkpoint = {
                **(bible.checkpoint or {}),
                "last_completed_stage": DramaStage.ASSETS.value,
                "resume_stage": DramaStage.EPISODE.value,
                "reason": "assets_approved",
                "updated_at": _now().isoformat(),
            }
        else:
            self._set_stage(bible, DramaStage.ASSETS, "awaiting_approval", "角色与场景等待确认")
            bible.current_stage = DramaStage.ASSETS.value
            bible.checkpoint = {
                **(bible.checkpoint or {}),
                "resume_stage": DramaStage.ASSETS.value,
                "reason": "awaiting_asset_approval",
                "updated_at": _now().isoformat(),
            }
        bible.approval_status = ApprovalStatus.IN_REVIEW.value

    @staticmethod
    def _mark_changed(entity: Any) -> None:
        if getattr(entity, "approval_status", None) == ApprovalStatus.APPROVED.value:
            entity.approval_status = ApprovalStatus.CHANGES_REQUESTED.value
            entity.approval_note = "内容已修改，请重新确认。"
            entity.approved_at = None

    @staticmethod
    def _approve(entity: Any, note: str | None) -> None:
        entity.approval_status = ApprovalStatus.APPROVED.value
        entity.approval_note = note.strip() if note else None
        entity.approved_at = _now()

    async def create_production_task(
        self,
        drama_id: str,
        payload: DramaProductionStartRequest,
    ) -> TaskModel:
        """Create the render-task projection for one approved Drama episode.

        Drama pre-production remains the source of truth. The regular Task and
        Scene tables are only a production projection so the shared durable
        renderer, artifact store, retry, and composition code can be reused.
        """

        bible = await self.get_detail(drama_id)
        if bible.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("Drama Storyboard 尚未批准，不能开始媒体生成。")
        episode = next(
            (item for item in bible.episodes if payload.episode_id is None or item.id == payload.episode_id),
            None,
        )
        if not episode:
            raise NotFoundException("Drama Episode", payload.episode_id or "default")
        if episode.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("当前 Drama Episode 尚未批准，不能进入制作。")
        if any(
            scene.approval_status != ApprovalStatus.APPROVED.value
            or any(shot.approval_status != ApprovalStatus.APPROVED.value for shot in scene.shots)
            for scene in episode.scenes
        ):
            raise ValidationException("只有已批准的 Scene 和 Shot 才能进入媒体生成。")

        checkpoint = dict(episode.checkpoint or {})
        existing_task_id = checkpoint.get("production_task_id")
        if existing_task_id and checkpoint.get("production_revision") == bible.revision:
            existing_task = await self.session.get(TaskModel, existing_task_id)
            if existing_task and existing_task.production_mode == ProductionMode.DRAMA.value:
                return existing_task

        project = await self.session.get(ProjectModel, bible.project_id)
        if not project:
            raise NotFoundException("Project", bible.project_id)
        template = template_catalog.get(payload.template_id)
        if not template:
            raise NotFoundException("Template", payload.template_id)
        if payload.bgm_asset_id:
            bgm = await self.session.get(AssetModel, payload.bgm_asset_id)
            if not bgm or (bgm.project_id not in {None, project.id}):
                raise ValidationException("背景音乐不存在或不属于当前项目。")
            if bgm.asset_type not in {AssetType.AUDIO.value, AssetType.BGM.value}:
                raise ValidationException("背景音乐必须是音频或 BGM 素材。")

        drafts = adapt_approved_shots_to_render_scenes(bible, episode_id=episode.id)
        if not drafts:
            raise ValidationException("当前 Episode 没有可制作的已批准 Shot。")
        task_id = _make_id("task")
        default_voice = payload.voice_id or project.default_voice_id
        if not default_voice:
            default_voice = await ProviderManager(self.session).get_default_tts_voice()
        content_mode = "generated_video" if payload.visual_mode == "video" else "generated_image"
        input_payload = {
            "production_mode": ProductionMode.DRAMA.value,
            "drama_id": bible.id,
            "episode_id": episode.id,
            "drama_revision": bible.revision,
            "visual_mode": payload.visual_mode,
            "content_mode": content_mode,
            "template_id": payload.template_id,
            "template_version": template["version"],
            "template_params": dict(payload.template_params or {}),
            "voice_id": default_voice,
            "speed": payload.speed,
            "voice_speed": payload.speed,
            "bgm_enabled": bool(payload.bgm_enabled),
            "bgm_asset_id": payload.bgm_asset_id if payload.bgm_enabled else None,
            "bgm_volume": payload.bgm_volume,
            "image_workflow_id": payload.image_workflow_id,
            "video_workflow_id": payload.video_workflow_id,
            "drama_production_version": 1,
        }
        task = TaskModel(
            id=task_id,
            project_id=project.id,
            title=episode.title,
            description=episode.synopsis or bible.logline,
            job_type=JobType.FULL_PIPELINE.value,
            production_mode=ProductionMode.DRAMA.value,
            status=TaskStatus.PENDING.value,
            progress_percentage=0,
            input_payload=input_payload,
        )
        self.session.add(task)
        for draft in drafts:
            metadata = {
                **(draft.production_metadata or {}),
                "drama": {
                    "drama_id": bible.id,
                    "episode_id": episode.id,
                    "revision": bible.revision,
                    "source_shot_id": draft.source_shot_id,
                },
                "media_status": "pending",
                "audio_status": "pending",
                "composition_status": "pending",
            }
            self.session.add(
                SceneModel(
                    id=_make_id("render_scene"),
                    task_id=task.id,
                    sequence_index=draft.sequence_index,
                    narration_text=draft.narration_text,
                    visual_prompt=draft.visual_prompt,
                    duration_seconds=draft.duration_seconds,
                    layout_params=dict(draft.layout_params or {}),
                    visual_role="context",
                    production_metadata=metadata,
                )
            )
        episode.checkpoint = {
            **checkpoint,
            "production_task_id": task.id,
            "production_revision": bible.revision,
            "production_status": TaskStatus.PENDING.value,
            "production_updated_at": _now().isoformat(),
        }
        bible.checkpoint = {
            **(bible.checkpoint or {}),
            "production_task_id": task.id,
            "production_episode_id": episode.id,
            "production_revision": bible.revision,
        }
        await self.session.flush()
        await self.session.commit()
        return task

    async def get_production_status(
        self,
        drama_id: str,
        episode_id: str | None = None,
    ) -> DramaProductionResponse:
        bible = await self.get_detail(drama_id)
        episode = next(
            (item for item in bible.episodes if episode_id is None or item.id == episode_id),
            None,
        )
        if not episode:
            raise NotFoundException("Drama Episode", episode_id or "default")
        task_id = (episode.checkpoint or {}).get("production_task_id")
        task = await self.session.get(TaskModel, task_id) if task_id else None
        job = None
        runs: list[WorkflowStepRunModel] = []
        artifacts = []
        if task:
            job = await self.session.scalar(
                select(WorkflowJobModel)
                .where(WorkflowJobModel.task_id == task.id)
                .order_by(WorkflowJobModel.created_at.desc())
                .limit(1)
            )
            runs = list(
                (
                    await self.session.scalars(
                        select(WorkflowStepRunModel)
                        .where(WorkflowStepRunModel.task_id == task.id)
                        .order_by(WorkflowStepRunModel.started_at, WorkflowStepRunModel.attempt)
                    )
                ).all()
            )
            from src.models.workflow import WorkflowArtifactModel

            subtitle_run_ids = [run.id for run in runs if run.step_key == "subtitles"]
            if subtitle_run_ids:
                artifacts = list(
                    (
                        await self.session.scalars(
                            select(WorkflowArtifactModel).where(
                                WorkflowArtifactModel.step_run_id.in_(subtitle_run_ids),
                                WorkflowArtifactModel.kind.in_(["srt", "ass", "timeline"]),
                            )
                        )
                    ).all()
                )
        latest: dict[tuple[str, str], WorkflowStepRunModel] = {}
        for run in runs:
            latest[(run.step_key, run.unit_key)] = run
        render_scenes = {
            (scene.production_metadata or {}).get("source_shot_id"): scene
            for scene in (task.scenes if task else [])
        }
        shot_rows: list[DramaShotProductionResponse] = []
        for drama_scene in episode.scenes:
            for shot in drama_scene.shots:
                render_scene = render_scenes.get(shot.id)
                unit = render_scene.id if render_scene else ""
                stage_runs = {
                    key: latest.get((key, unit))
                    for key in ("media", "audio", "composition")
                }
                statuses = {
                    key: (run.status if run else "pending")
                    for key, run in stage_runs.items()
                }
                failed_run = next((run for run in stage_runs.values() if run and run.status == "failed"), None)
                qa = list((render_scene.production_metadata or {}).get("qa") or []) if render_scene else []
                if failed_run:
                    status = "failed"
                elif statuses["composition"] in {"completed", "completed_with_warning", "reused", "skipped"}:
                    status = "completed"
                elif any(value in {"running"} for value in statuses.values()):
                    status = "running"
                elif any(value in {"completed", "completed_with_warning", "reused"} for value in statuses.values()):
                    status = "in_progress"
                else:
                    status = "pending"
                shot_rows.append(
                    DramaShotProductionResponse(
                        shot_id=render_scene.id if render_scene else shot.id,
                        source_shot_id=shot.id,
                        sequence_index=shot.sequence_index,
                        status=status,
                        media_status=statuses["media"],
                        audio_status=statuses["audio"],
                        composition_status=statuses["composition"],
                        media_asset_id=render_scene.media_asset_id if render_scene else None,
                        audio_asset_id=render_scene.audio_asset_id if render_scene else None,
                        rendered_segment_asset_id=render_scene.rendered_segment_asset_id if render_scene else None,
                        duration_seconds=render_scene.duration_seconds if render_scene else shot.duration_hint,
                        dialogue_line_count=len(shot.dialogue_lines),
                        dialogue_timeline=list((render_scene.layout_params or {}).get("dialogue_timeline") or []) if render_scene else [],
                        qa=qa,
                        error_message=failed_run.error_message if failed_run else None,
                    )
                )

        result_payload = dict((task.result_payload if task else {}) or {})
        qa_before = list(result_payload.get("qa_before") or [])
        qa_after = list(result_payload.get("qa_after") or [])
        if not qa_before:
            before_run = latest.get(("qa_before", ""))
            qa_before = list((before_run.output_payload or {}).get("findings") or []) if before_run else []
        if not qa_after:
            after_run = latest.get(("qa_after", ""))
            qa_after = list((after_run.output_payload or {}).get("findings") or []) if after_run else []
        final_url = result_payload.get("final_video_url")
        if not final_url and result_payload.get("final_video_path"):
            final_url = local_storage.get_url(result_payload["final_video_path"])
        status = task.status if task else "not_started"
        if task and job and job.status in {"queued", "running", "retrying"}:
            status = job.status
        return DramaProductionResponse(
            drama_id=bible.id,
            episode_id=episode.id,
            task_id=task.id if task else None,
            job_id=job.id if job else None,
            status=status,
            progress=(job.progress if job else (task.progress_percentage if task else 0)),
            current_stage=job.current_stage if job else None,
            shots=shot_rows,
            qa_before=qa_before,
            qa_after=qa_after,
            final_video_asset_id=result_payload.get("final_video_asset_id"),
            final_video_url=final_url,
            subtitle_artifact_ids=result_payload.get("subtitle_artifact_ids")
            or [artifact.id for artifact in artifacts],
            total_duration_seconds=result_payload.get("total_duration_seconds"),
            error_message=(task.error_message if task else None) or (job.error_message if job else None),
        )
