"""Durable post-approval production for Drama Episodes.

The Drama Bible remains the source of truth. This pipeline only projects an
approved Episode into the existing Task/Scene renderer and records every
shot-level output through the shared WorkflowRuntime.
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from src.core.exceptions import ValidationException
from src.domain.drama import ApprovalStatus
from src.domain.enums import AssetType, ProductionMode
from src.domain.production_workflows import DRAMA_PRODUCTION_WORKFLOW
from src.models.asset import AssetModel
from src.models.drama import DramaEpisodeModel
from src.models.workflow import WorkflowArtifactModel, WorkflowJobModel, WorkflowStepRunModel
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.services.drama_production_service import DramaProductionService
from src.services.drama_render_adapter import (
    RenderSceneDraft,
    adapt_approved_shots_to_render_scenes,
)
from src.services.durable_pipeline import DurableProductionPipeline, subtitle_documents
from src.services.generation_service import GenerationService
from src.services.media_probe import media_probe_service
from src.services.provider_manager import ProviderManager
from src.services.rendering_service import RenderingService
from src.services.workflow_execution import WorkflowExecutionContext, assert_task_editable
from src.services.workflow_runtime import ArtifactSpec, WorkflowRuntime, sha256_file
from src.tasks.broadcaster import event_broadcaster


class DramaProductionPipeline(DurableProductionPipeline):
    """Shot → media → mixed audio → episode video durable pipeline."""

    production_mode = ProductionMode.DRAMA
    workflow = DRAMA_PRODUCTION_WORKFLOW
    # A failed shot is recorded and the remaining units continue. The next
    # explicit retry creates a new durable attempt without waiting through the
    # Knowledge pipeline's long external-provider retry delays.
    retry_delays = (0, 0, 0)

    def __init__(self, session, job, rendering_service_factory=None):
        super().__init__(session, job, rendering_service_factory)
        self.workflow = DRAMA_PRODUCTION_WORKFLOW

    async def _initialize(self):
        job_id, task_id = self.job.id, self.job.task_id
        db_job = await self.db.get(WorkflowJobModel, job_id)
        if db_job is None:
            await assert_task_editable(self.db, task_id)
            token = getattr(self.job, "lease_token", None) or f"lease_{job_id}"
            self.job.lease_token = token
            self.owns_job = True
            db_job = WorkflowJobModel(
                id=job_id,
                task_id=task_id,
                job_type=self.job.job_type,
                status="running",
                lease_token=token,
                params=self.params,
            )
            self.db.add(db_job)
            await self.db.commit()
        token = getattr(self.job, "lease_token", None)
        if not token or token != db_job.lease_token:
            raise ValidationException("任务缺少有效执行租约。")

        self.context = WorkflowExecutionContext(job_id, token)
        renderer = (
            self.rendering_factory(self.db)
            if self.rendering_factory
            else RenderingService(self.db, execution_context=self.context, durable=True)
        )
        renderer.execution_context, renderer.durable = self.context, True
        renderer.asset_service.execution_context = self.context
        self.storage = renderer.storage
        self.renderer = renderer
        self.runtime = WorkflowRuntime(self.db, self.storage.base_dir, job_id, token, self.workflow)
        await self.runtime.assert_lease()
        task = await TaskRepository(self.db).get_by_id(task_id)
        if not task:
            raise ValidationException("任务不存在")
        if task.production_mode != ProductionMode.DRAMA.value:
            raise ValidationException("Drama Pipeline 不能执行其他生产模式任务。")
        payload = dict(task.input_payload or {})
        self.drama_id = str(payload.get("drama_id") or "")
        self.episode_id = str(payload.get("episode_id") or "")
        if not self.drama_id or not self.episode_id:
            raise ValidationException("Drama 任务缺少 drama_id 或 episode_id。")

        provider_manager = ProviderManager(self.db, snapshot=payload.get("workflow_provider_snapshot")) if payload.get("workflow_provider_snapshot") else ProviderManager(self.db)
        if payload.get("workflow_provider_snapshot"):
            await provider_manager.capture_snapshot()
        else:
            snapshot = await provider_manager.capture_snapshot()
            payload["workflow_provider_snapshot"] = snapshot
            task.input_payload = payload
            await self.save()
        self.provider_inputs = provider_manager.snapshot_fingerprint_payload()
        self.gen = GenerationService(
            self.db,
            storage=self.storage,
            provider_manager=provider_manager,
            execution_context=self.context,
            task_id=task_id,
            job_id=job_id,
        )
        self.task = task
        self.payload = payload
        return task

    async def _load_source(self):
        detail = await DramaProductionService(self.db).get_detail(self.drama_id)
        if detail.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("Drama Storyboard 尚未批准，不能进入媒体生成。")
        episode = next((item for item in detail.episodes if item.id == self.episode_id), None)
        if not episode:
            raise ValidationException("Drama Episode 不存在或不属于当前 Drama Bible。")
        if episode.approval_status != ApprovalStatus.APPROVED.value:
            raise ValidationException("Drama Episode 尚未批准，不能进入媒体生成。")
        for scene in episode.scenes:
            if scene.approval_status != ApprovalStatus.APPROVED.value:
                raise ValidationException("未批准的 Drama Scene 不能进入媒体生成。")
            for shot in scene.shots:
                if shot.approval_status != ApprovalStatus.APPROVED.value:
                    raise ValidationException(f"Shot {shot.id} 尚未批准，不能进入媒体生成。")
        drafts = adapt_approved_shots_to_render_scenes(detail, episode_id=episode.id)
        shots = {shot.id: shot for scene in episode.scenes for shot in scene.shots}
        return detail, episode, drafts, shots

    async def _reference_inputs(self, draft: RenderSceneDraft) -> list[dict[str, Any]]:
        references: list[dict[str, Any]] = []
        metadata = draft.production_metadata or {}
        character_rows = metadata.get("character_consistency") or []
        for row in character_rows:
            if row.get("reference_asset_id"):
                references.append({"role": "character", **row})
        location = metadata.get("location_consistency") or {}
        for asset_id in location.get("reference_asset_ids") or []:
            references.append({"role": "location", "reference_asset_id": asset_id})
        result: list[dict[str, Any]] = []
        for item in references:
            asset = await self.db.get(AssetModel, item["reference_asset_id"])
            row = {key: value for key, value in item.items() if key != "canonical_description"}
            row["asset_exists"] = bool(asset)
            row["path_exists"] = bool(asset and self.storage.get_path(asset.file_path).is_file())
            row["sha256"] = await sha256_file(self.storage.get_path(asset.file_path)) if row["path_exists"] else None
            row["path"] = str(self.storage.get_path(asset.file_path)) if row["path_exists"] else None
            result.append(row)
        return result

    @staticmethod
    def _finding(
        key: str,
        label: str,
        passed: bool,
        message: str,
        *,
        severity: str = "warning",
        shot_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "severity": severity,
            "passed": bool(passed),
            "message": message,
            "shot_id": shot_id,
        }

    async def _before_qa(self, detail, episode, drafts, shots):
        findings: list[dict[str, Any]] = []
        by_shot: dict[str, list[dict[str, Any]]] = {}
        characters = {character.id: character for character in detail.characters}
        locations = {location.id: location for location in detail.locations}
        for draft in drafts:
            shot = shots[draft.source_shot_id]
            shot_findings: list[dict[str, Any]] = []
            consistency = draft.production_metadata.get("character_consistency") or []
            complete = bool(consistency) or not shot.character_ids
            for row in consistency:
                character = characters.get(row.get("id"))
                complete = complete and bool(
                    character
                    and character.description.strip()
                    and character.appearance_lock.strip()
                    and character.wardrobe.strip()
                    and row.get("prompt_anchor")
                )
                reference_id = row.get("reference_asset_id")
                if reference_id:
                    asset = await self.db.get(AssetModel, reference_id)
                    exists = bool(asset and self.storage.get_path(asset.file_path).is_file())
                    shot_findings.append(
                        self._finding(
                            "missing_character_asset",
                            "Character reference asset",
                            exists,
                            "角色参考资产可用。" if exists else "已配置的角色参考资产缺失。",
                            severity="blocking" if not exists else "info",
                            shot_id=shot.id,
                        )
                    )
                else:
                    shot_findings.append(
                        self._finding(
                            "missing_character_asset",
                            "Character reference asset",
                            False,
                            f"角色 {row.get('name') or '未命名'} 没有参考图，将使用 deterministic prompt anchor。",
                            severity="warning",
                            shot_id=shot.id,
                        )
                    )
            shot_findings.append(
                self._finding(
                    "character_consistency",
                    "Character consistency metadata",
                    complete,
                    "canonical description、appearance、wardrobe 和 anchor 已注入。"
                    if complete
                    else "角色一致性字段不完整。",
                    severity="blocking" if not complete else "info",
                    shot_id=shot.id,
                )
            )
            location = locations.get(shot.location_id or "")
            location_ok = bool(location and location.prompt_anchor and draft.production_metadata.get("location_consistency"))
            shot_findings.append(
                self._finding(
                    "location_anchor",
                    "Location anchor",
                    location_ok,
                    "Location anchor 已注入。" if location_ok else "Shot 缺少 Location anchor。",
                    severity="blocking" if not location_ok else "info",
                    shot_id=shot.id,
                )
            )
            duration_ok = float(draft.duration_seconds or 0) > 0
            shot_findings.append(
                self._finding(
                    "duration",
                    "Duration",
                    duration_ok,
                    "Shot 时长有效。" if duration_ok else "Shot 时长必须大于 0。",
                    severity="blocking" if not duration_ok else "info",
                    shot_id=shot.id,
                )
            )
            dialogue_ok = all(line.text.strip() for line in shot.dialogue_lines)
            shot_findings.append(
                self._finding(
                    "dialogue",
                    "Dialogue lines",
                    dialogue_ok,
                    f"已登记 {len(shot.dialogue_lines)} 条 DialogueLine。"
                    if dialogue_ok
                    else "存在空 DialogueLine。",
                    severity="blocking" if not dialogue_ok else "info",
                    shot_id=shot.id,
                )
            )
            for line in shot.dialogue_lines:
                character = characters.get(line.character_id or "") if line.character_id else None
                if line.character_id and not character:
                    shot_findings.append(
                        self._finding(
                            "dialogue_character",
                            "Dialogue character",
                            False,
                            f"DialogueLine {line.id} 引用了不存在的 Character。",
                            severity="blocking",
                            shot_id=shot.id,
                        )
                    )
                elif line.character_id and not character.voice_id:
                    shot_findings.append(
                        self._finding(
                            "voice_id",
                            "Character voice_id",
                            False,
                            f"角色 {character.name} 未配置 voice_id，将回退到任务默认音色。",
                            severity="warning",
                            shot_id=shot.id,
                        )
                    )
            continuity_ok = bool(draft.production_metadata.get("prompt_anchor"))
            shot_findings.append(
                self._finding(
                    "continuity",
                    "Continuity input",
                    continuity_ok,
                    "Shot anchor 与抽象 continuity input 已准备。"
                    if continuity_ok
                    else "缺少 Shot continuity anchor。",
                    severity="blocking" if not continuity_ok else "info",
                    shot_id=shot.id,
                )
            )
            by_shot[shot.id] = shot_findings
            findings.extend(shot_findings)
        return findings, by_shot

    async def _mark_scene(self, scene_id: str, **changes: Any) -> None:
        scene = await SceneRepository(self.db).get_by_id(scene_id)
        if not scene:
            return
        metadata = {**(scene.production_metadata or {}), **changes}
        scene.production_metadata = metadata
        await self.save()

    async def _stage_media(self, task, drafts, scenes_by_source, *, content_mode: str):
        outputs_by_scene: dict[str, list] = {}
        errors: list[str] = []
        for draft in drafts:
            scene = scenes_by_source[draft.source_shot_id]
            references = await self._reference_inputs(draft)
            missing_reference = next(
                (item for item in references if not item.get("asset_exists") or not item.get("path_exists")),
                None,
            )
            if missing_reference:
                role = "角色" if missing_reference.get("role") == "character" else "场景"
                raise ValidationException(
                    f"{role}参考资产 {missing_reference.get('reference_asset_id')} 不存在或文件缺失；"
                    "请重新上传或清除参考资产后再生成，不能静默退回文生图。"
                )
            reference = next((item for item in references if item.get("path_exists")), None)
            continuity = dict(draft.layout_params.get("continuity_input") or {})
            last_frame_asset_id = continuity.get("last_frame_asset_id")
            if last_frame_asset_id:
                last_frame_asset = await self.db.get(AssetModel, last_frame_asset_id)
                if last_frame_asset:
                    last_frame_path = self.storage.get_path(last_frame_asset.file_path)
                    if last_frame_path.is_file():
                        continuity["last_frame_path"] = str(last_frame_path)
            # The current bundled Providers do not expose a last-frame input.
            # Keep the abstract previous-shot reference stable so retrying one
            # Shot does not invalidate an already successful neighboring Shot.
            provider_key = self.provider_inputs.get(
                "video" if content_mode == "generated_video" else "image"
            )
            inputs = {
                "source_shot_id": draft.source_shot_id,
                "content_mode": content_mode,
                "prompt": draft.visual_prompt,
                "prompt_anchor": draft.production_metadata.get("prompt_anchor"),
                "character_consistency": draft.production_metadata.get("character_consistency"),
                "location_consistency": draft.production_metadata.get("location_consistency"),
                "reference_assets": [{key: value for key, value in item.items() if key != "path"} for item in references],
                "continuity_input": continuity,
                "provider": provider_key,
                "workflow": self.payload.get(
                    "video_workflow_id"
                    if content_mode == "generated_video"
                    else "image_workflow_id"
                ),
            }

            async def action(run, scene_id=scene.id, draft=draft, reference=reference, continuity=continuity):
                current = await SceneRepository(self.db).get_by_id(scene_id)
                if not current:
                    raise ValidationException("Drama Render Scene 不存在。")
                if content_mode == "generated_video":
                    if reference and not current.media_asset_id:
                        # Existing video Providers already accept image_url as
                        # a first-frame input. Keep this as an adapter-level
                        # capability; a dedicated last-frame Provider remains optional.
                        current.media_asset_id = reference["reference_asset_id"]
                        await self.db.flush()
                    await self.gen.generate_scene_video(
                        current.id,
                        prompt_override=draft.visual_prompt,
                        continuity_input=continuity,
                    )
                else:
                    await self.gen.generate_scene_image(
                        current.id,
                        prompt_override=draft.visual_prompt,
                        reference_image_path=reference.get("path") if reference else None,
                        continuity_input=continuity,
                    )
                await self.save()
                current = await SceneRepository(self.db).get_by_id(scene_id)
                asset, _ = await self.asset(current.media_asset_id)
                return [
                    ArtifactSpec(
                        self.storage.get_path(asset.file_path),
                        "drama_media",
                        asset.id,
                        "generated",
                    )
                ], {"asset_id": asset.id, "reference_strategy": "provider_or_deterministic_anchor"}, None, False

            try:
                _, outputs = await self.stage(
                    "media",
                    inputs,
                    action,
                    unit=scene.id,
                )
                outputs_by_scene[scene.id] = outputs
                artifact = outputs[0] if outputs else None
                current = await SceneRepository(self.db).get_by_id(scene.id)
                if artifact and artifact.asset_id:
                    await self.bind(current, "media_asset_id", [artifact])
                await self._mark_scene(scene.id, media_status="completed", media_error=None)
            except Exception as exc:
                message = str(exc)
                errors.append(f"{draft.source_shot_id}: {message}")
                await self._mark_scene(scene.id, media_status="failed", media_error=message)
        return outputs_by_scene, errors

    async def _synthesize(self, provider, text: str, voice_id: str | None, speed: float):
        try:
            return await provider.synthesize(text, voice_id=voice_id, speed=speed)
        except TypeError:
            return await provider.synthesize(text, voice_id=voice_id)

    async def _stage_audio(self, task, drafts, shots_by_source, scenes_by_source):
        outputs_by_scene: dict[str, list] = {}
        errors: list[str] = []
        has_dialogue = any(shot.dialogue_lines for shot in shots_by_source.values())
        tts_provider = await self.gen._get_tts_provider() if has_dialogue else None
        default_voice = self.payload.get("voice_id")
        if has_dialogue and not default_voice:
            default_voice = await self.gen.provider_manager.get_default_tts_voice()
        for draft in drafts:
            scene = scenes_by_source[draft.source_shot_id]
            shot = shots_by_source[draft.source_shot_id]
            line_inputs = []
            for line in shot.dialogue_lines:
                character = line.character
                voice_id = character.voice_id if character else default_voice
                line_inputs.append({
                    "id": line.id,
                    "sequence_index": line.sequence_index,
                    "speaker_name": line.speaker_name,
                    "text": line.text,
                    "character_id": line.character_id,
                    "voice_id": voice_id,
                    "delivery": line.delivery,
                })
            inputs = {
                "source_shot_id": draft.source_shot_id,
                "lines": line_inputs,
                "speed": self.payload.get("speed", 1.0),
                "provider": self.provider_inputs.get("tts"),
            }

            async def action(run, scene_id=scene.id, shot=shot, line_inputs=line_inputs):
                current = await SceneRepository(self.db).get_by_id(scene_id)
                if not current:
                    raise ValidationException("Drama Render Scene 不存在。")
                if not line_inputs:
                    if float(current.duration_seconds or 0) <= 0:
                        raise ValidationException("没有对白的 Shot 需要有效时长。")
                    current.layout_params = {**(current.layout_params or {}), "dialogue_timeline": []}
                    await self.save()
                    return [], {"duration_seconds": current.duration_seconds, "dialogue_timeline": []}, None, True

                line_assets: list[AssetModel] = []
                timeline: list[dict[str, Any]] = []
                cursor = 0.0
                for line in line_inputs:
                    if tts_provider is None:
                        raise ValidationException("存在对白但没有可用的 TTS Provider。")
                    result = await self._synthesize(
                        tts_provider,
                        line["text"],
                        line["voice_id"],
                        float(self.payload.get("speed", 1.0)),
                    )
                    if not result.audio_bytes:
                        raise ValidationException(f"DialogueLine {line['id']} 返回空音频。")
                    asset = await self.gen.asset_service.save_asset(
                        content=result.audio_bytes,
                        file_name=f"drama_line_{line['id']}.{result.format}",
                        mime_type=result.mime_type,
                        asset_type=AssetType.AUDIO,
                        project_id=task.project_id,
                        duration_seconds=float(result.duration_seconds or 0) or None,
                        metadata={
                            "drama_id": self.drama_id,
                            "episode_id": self.episode_id,
                            "scene_id": scene_id,
                            "shot_id": shot.id,
                            "dialogue_line_id": line["id"],
                            "voice_id": line["voice_id"],
                            "provider": getattr(tts_provider, "name", "unknown"),
                        },
                    )
                    await self.save()
                    probe = await media_probe_service.probe(self.storage.get_path(asset.file_path))
                    duration = float(probe.audio_duration or result.duration_seconds or 0)
                    if duration <= 0:
                        raise ValidationException(f"DialogueLine {line['id']} 没有有效音频时长。")
                    line_assets.append(asset)
                    timeline.append({
                        **line,
                        "start": round(cursor, 3),
                        "end": round(cursor + duration, 3),
                        "duration_seconds": round(duration, 3),
                    })
                    cursor += duration

                mix_path = self.runtime.attempt_dir(run) / "shot_audio.wav"
                source_paths = [self.storage.get_path(asset.file_path) for asset in line_assets]
                if len(source_paths) == 1:
                    await asyncio.to_thread(shutil.copyfile, source_paths[0], mix_path)
                else:
                    command = ["ffmpeg", "-y"]
                    for path in source_paths:
                        command.extend(["-i", str(path)])
                    filters = [
                        f"[{index}:a]aresample=async=1:first_pts=0,asetpts=PTS-STARTPTS[a{index}]"
                        for index in range(len(source_paths))
                    ]
                    labels = "".join(f"[a{index}]" for index in range(len(source_paths)))
                    filters.append(f"{labels}concat=n={len(source_paths)}:v=0:a=1[a]")
                    command.extend([
                        "-filter_complex", ";".join(filters),
                        "-map", "[a]", "-c:a", "pcm_s16le", str(mix_path),
                    ])
                    await self.renderer._run_ffmpeg_command(command, mix_path, timeout=120.0)
                mixed_probe = await media_probe_service.probe(mix_path)
                mixed_duration = float(mixed_probe.audio_duration or cursor)
                mixed_asset = await self.gen.asset_service.save_asset_from_file(
                    mix_path,
                    file_name=f"drama_shot_audio_{shot.id}.wav",
                    mime_type="audio/wav",
                    asset_type=AssetType.AUDIO,
                    project_id=task.project_id,
                    duration_seconds=mixed_duration,
                    metadata={
                        "drama_id": self.drama_id,
                        "episode_id": self.episode_id,
                        "shot_id": shot.id,
                        "dialogue_line_ids": [line["id"] for line in line_inputs],
                        "voice_ids": [line["voice_id"] for line in line_inputs],
                        "duration_source": "ffprobe",
                    },
                )
                current.duration_seconds = max(float(current.duration_seconds or 0), mixed_duration)
                current.layout_params = {
                    **(current.layout_params or {}),
                    "dialogue_timeline": timeline,
                    "audio_mix": "sequential_dialogue_lines",
                    "audio_actual_duration_seconds": mixed_duration,
                    "duration_source": "dialogue_audio_probe",
                }
                await self.save()
                specs = [
                    ArtifactSpec(self.storage.get_path(asset.file_path), "dialogue_line", asset.id, "generated")
                    for asset in line_assets
                ]
                specs.append(ArtifactSpec(self.storage.get_path(mixed_asset.file_path), "shot_audio", mixed_asset.id, "generated"))
                return specs, {
                    "asset_id": mixed_asset.id,
                    "dialogue_timeline": timeline,
                    "duration_seconds": mixed_duration,
                }, None, False

            try:
                _, outputs = await self.stage("audio", inputs, action, unit=scene.id)
                outputs_by_scene[scene.id] = outputs
                final_audio = next((item for item in reversed(outputs) if item.kind == "shot_audio"), None)
                current = await SceneRepository(self.db).get_by_id(scene.id)
                if final_audio and final_audio.asset_id:
                    await self.bind(current, "audio_asset_id", [final_audio])
                await self._mark_scene(scene.id, audio_status="completed", audio_error=None)
            except Exception as exc:
                message = str(exc)
                errors.append(f"{draft.source_shot_id}: {message}")
                await self._mark_scene(scene.id, audio_status="failed", audio_error=message)
        return outputs_by_scene, errors

    async def _stage_subtitles(self, task, scenes, audio_outputs=None):
        timeline: list[dict[str, Any]] = []
        offset = 0.0
        for scene in scenes:
            for line in (scene.layout_params or {}).get("dialogue_timeline") or []:
                text = line["text"] if line.get("speaker_name") == "旁白" else f"{line.get('speaker_name')}: {line['text']}"
                timeline.append({
                    "shot_id": (scene.production_metadata or {}).get("source_shot_id"),
                    "dialogue_line_id": line.get("id"),
                    "speaker_name": line.get("speaker_name"),
                    "text": text,
                    "start": round(offset + float(line["start"]), 3),
                    "end": round(offset + float(line["end"]), 3),
                })
            offset += max(0.1, float(scene.duration_seconds or 0))

        async def action(run):
            srt, ass = subtitle_documents(timeline)
            directory = self.runtime.attempt_dir(run)
            specs = []
            if timeline:
                for name, data in (("subtitles.srt", srt), ("subtitles.ass", ass)):
                    target = directory / name
                    temporary = target.with_suffix(target.suffix + ".tmp")
                    await asyncio.to_thread(temporary.write_text, data, encoding="utf-8")
                    temporary.replace(target)
                    specs.append(ArtifactSpec(target, name.rsplit(".", 1)[-1]))
            path = await self.runtime.write_json(run, "timeline.json", timeline)
            specs.append(ArtifactSpec(path, "timeline"))
            return specs, {"timeline": timeline}, None, False

        _, artifacts = await self.stage(
            "subtitles",
            {"timeline": timeline, "dialogue_line_count": len(timeline)},
            action,
            dependencies=[
                artifact
                for outputs in (audio_outputs or {}).values()
                for artifact in outputs
            ],
        )
        return timeline, artifacts

    async def _after_qa(self, drafts, scenes_by_source, media_errors, audio_errors, timeline):
        findings: list[dict[str, Any]] = []
        for source_id, scene in scenes_by_source.items():
            metadata = scene.production_metadata or {}
            media_ok = bool(scene.media_asset_id)
            audio_lines = (metadata.get("dialogue_lines") or [])
            audio_ok = bool(scene.audio_asset_id) if audio_lines else True
            timeline_lines = (scene.layout_params or {}).get("dialogue_timeline") or []
            duration_ok = float(scene.duration_seconds or 0) > 0
            continuity_ok = bool(metadata.get("prompt_anchor"))
            shot_findings = [
                self._finding("media", "Shot media", media_ok, "媒体资产已登记。" if media_ok else "媒体资产缺失。", severity="blocking" if not media_ok else "info", shot_id=source_id),
                self._finding("audio", "Shot audio", audio_ok, "对白已混合为 shot audio artifact。" if audio_ok else "有对白但缺少 shot audio artifact。", severity="blocking" if not audio_ok else "info", shot_id=source_id),
                self._finding("duration", "Measured duration", duration_ok, "时长有效。" if duration_ok else "缺少有效时长。", severity="blocking" if not duration_ok else "info", shot_id=source_id),
                self._finding("dialogue_timing", "Dialogue timing", len(timeline_lines) == len(audio_lines), f"已生成 {len(timeline_lines)} 条真实 DialogueLine timing。", severity="blocking" if len(timeline_lines) != len(audio_lines) else "info", shot_id=source_id),
                self._finding("continuity", "Continuity", continuity_ok, "连续性 metadata 保留。" if continuity_ok else "连续性 metadata 缺失。", severity="blocking" if not continuity_ok else "info", shot_id=source_id),
            ]
            metadata = {**metadata, "qa_after": shot_findings}
            scene.production_metadata = metadata
            findings.extend(shot_findings)
        if media_errors:
            findings.append(self._finding("media_errors", "Media failures", False, "；".join(media_errors), severity="blocking"))
        if audio_errors:
            findings.append(self._finding("audio_errors", "Audio failures", False, "；".join(audio_errors), severity="blocking"))
        return findings

    @staticmethod
    def _has_blocking(findings: list[dict[str, Any]]) -> bool:
        return any(item.get("severity") == "blocking" and not item.get("passed") for item in findings)

    async def _stage_composition(self, task, drafts, scenes_by_source, media_outputs, audio_outputs):
        clips = []
        errors: list[str] = []
        for draft in drafts:
            scene = scenes_by_source[draft.source_shot_id]
            dependencies = [*media_outputs.get(scene.id, []), *audio_outputs.get(scene.id, [])]
            inputs = {
                "source_shot_id": draft.source_shot_id,
                "duration_seconds": scene.duration_seconds,
                "layout": scene.layout_params,
                "template_id": self.payload.get("template_id"),
                "content_mode": self.payload.get("content_mode"),
                "composition_format_version": RenderingService.COMPOSITION_FORMAT_VERSION,
            }

            async def action(run, scene_id=scene.id):
                current = await SceneRepository(self.db).get_by_id(scene_id)
                if not current:
                    raise ValidationException("Drama Render Scene 不存在，无法合成。")
                self.renderer.commands = []
                await self.renderer.render_scene_clip(scene_id)
                await self.save()
                current = await SceneRepository(self.db).get_by_id(scene_id)
                asset, _ = await self.asset(current.rendered_segment_asset_id)
                return [ArtifactSpec(self.storage.get_path(asset.file_path), "scene_clip", asset.id)], {"asset_id": asset.id, "ffmpeg_commands": self.renderer.commands}, None, False

            try:
                _, outputs = await self.stage("composition", inputs, action, unit=scene.id, dependencies=dependencies)
                clip = outputs[0] if outputs else None
                if clip:
                    clips.append(clip)
                    current = await SceneRepository(self.db).get_by_id(scene.id)
                    await self.bind(current, "rendered_segment_asset_id", [clip])
                await self._mark_scene(scene.id, composition_status="completed", composition_error=None)
            except Exception as exc:
                message = str(exc)
                errors.append(f"{draft.source_shot_id}: {message}")
                await self._mark_scene(scene.id, composition_status="failed", composition_error=message)
        if errors:
            return clips, errors, None

        async def final_action(run):
            self.renderer.commands = []
            asset = await self.renderer.compose_task_video(
                task.id,
                bgm_asset_id=self.payload.get("bgm_asset_id") if self.payload.get("bgm_enabled") else None,
            )
            await self.save()
            return [ArtifactSpec(self.storage.get_path(asset.file_path), "final_video", asset.id)], {"asset_id": asset.id, "ffmpeg_commands": self.renderer.commands}, None, False

        _, final_outputs = await self.stage(
            "composition",
            {
                "clip_order": [item.sha256 for item in clips],
                "bgm_asset_id": self.payload.get("bgm_asset_id") if self.payload.get("bgm_enabled") else None,
                "composition_format_version": RenderingService.COMPOSITION_FORMAT_VERSION,
            },
            final_action,
            dependencies=clips,
        )
        return clips, errors, final_outputs

    async def _mark_failed(self, error: Exception, qa_before=None, qa_after=None) -> None:
        if not getattr(self, "runtime", None):
            return
        try:
            await self.runtime.assert_lease()
            task = await TaskRepository(self.db).get_by_id(self.job.task_id)
            if task:
                task.status = "failed"
                task.error_message = str(error)
                task.result_payload = {
                    **(task.result_payload or {}),
                    "video_status": "failed",
                    "drama_id": self.drama_id,
                    "episode_id": self.episode_id,
                    "qa_before": qa_before or (task.result_payload or {}).get("qa_before", []),
                    "qa_after": qa_after or (task.result_payload or {}).get("qa_after", []),
                }
            episode = await self.db.get(DramaEpisodeModel, self.episode_id)
            if episode:
                episode.checkpoint = {**(episode.checkpoint or {}), "production_status": "failed", "production_error": str(error)}
            await self.db.commit()
            await event_broadcaster.broadcast(
                "task.failed",
                {"task_id": self.job.task_id, "job_id": self.job.id, "status": "failed", "error": str(error)},
                task_id=self.job.task_id,
                job_id=self.job.id,
                lease_token=self.runtime.lease_token,
            )
        except Exception:
            await self.db.rollback()

    async def execute(self) -> dict[str, Any]:
        task = await self._initialize()
        try:
            detail, episode, drafts, shots_by_source = await self._load_source()
            await self.runtime.assert_lease()
            task.status = "running"
            task.started_at = task.started_at or datetime.now(UTC)
            await self.save()
            await event_broadcaster.broadcast(
                "task.started",
                {"task_id": task.id, "job_id": self.job.id, "status": "running", "progress": 0},
                task_id=task.id,
                job_id=self.job.id,
                lease_token=self.runtime.lease_token,
            )
            render_scenes = list(await SceneRepository(self.db).list_by_task_id(task.id))
            scenes_by_source = {
                (scene.production_metadata or {}).get("source_shot_id"): scene
                for scene in render_scenes
            }
            if set(scenes_by_source) != {draft.source_shot_id for draft in drafts}:
                raise ValidationException("Drama Task 与批准的 Shot 映射不一致，请重新创建生产任务。")

            before_inputs = {
                "drama_id": self.drama_id,
                "episode_id": self.episode_id,
                "revision": detail.revision,
                "shots": [
                    {
                        "source_shot_id": draft.source_shot_id,
                        "prompt": draft.visual_prompt,
                        "metadata": draft.production_metadata,
                    }
                    for draft in drafts
                ],
                "provider": self.provider_inputs,
            }
            before_findings: list[dict[str, Any]] = []
            before_by_shot: dict[str, list[dict[str, Any]]] = {}

            async def before_action(run):
                nonlocal before_findings, before_by_shot
                before_findings, before_by_shot = await self._before_qa(detail, episode, drafts, shots_by_source)
                path = await self.runtime.write_json(run, "qa_before.json", {"findings": before_findings})
                return [ArtifactSpec(path, "qa_before")], {"findings": before_findings}, None, False

            await self.stage("qa_before", before_inputs, before_action)
            for source_id, findings in before_by_shot.items():
                await self._mark_scene(scenes_by_source[source_id].id, qa=findings, qa_before=findings)
            if self._has_blocking(before_findings):
                raise ValidationException("生成前 QA 未通过，已阻止媒体生成。")

            content_mode = self.payload.get("content_mode") or "generated_image"
            media_outputs, media_errors = await self._stage_media(
                task, drafts, scenes_by_source, content_mode=content_mode
            )
            audio_outputs, audio_errors = await self._stage_audio(
                task, drafts, shots_by_source, scenes_by_source
            )
            render_scenes = list(await SceneRepository(self.db).list_by_task_id(task.id))
            timeline, subtitle_artifacts = await self._stage_subtitles(task, render_scenes, audio_outputs)
            after_inputs = {
                "media_errors": media_errors,
                "audio_errors": audio_errors,
                "timeline": timeline,
                "scenes": [
                    {
                        "id": scene.id,
                        "source_shot_id": (scene.production_metadata or {}).get("source_shot_id"),
                        "media_asset_id": scene.media_asset_id,
                        "audio_asset_id": scene.audio_asset_id,
                        "duration_seconds": scene.duration_seconds,
                        "dialogue_timeline": (scene.layout_params or {}).get("dialogue_timeline", []),
                    }
                    for scene in render_scenes
                ],
            }
            after_findings: list[dict[str, Any]] = []

            async def after_action(run):
                nonlocal after_findings
                after_findings = await self._after_qa(
                    drafts,
                    {source: await SceneRepository(self.db).get_by_id(scene.id) for source, scene in scenes_by_source.items()},
                    media_errors,
                    audio_errors,
                    timeline,
                )
                path = await self.runtime.write_json(run, "qa_after.json", {"findings": after_findings})
                return [ArtifactSpec(path, "qa_after")], {"findings": after_findings}, None, False

            await self.stage("qa_after", after_inputs, after_action)
            if self._has_blocking(after_findings):
                raise ValidationException("生成后 QA 未通过，已阻止 Episode 合成。")

            clips, composition_errors, final_outputs = await self._stage_composition(
                task, drafts, scenes_by_source, media_outputs, audio_outputs
            )
            if composition_errors or not final_outputs:
                raise ValidationException("部分 Shot 合成失败，Episode 暂未生成最终视频。")
            final_artifact = final_outputs[0]
            final_info = dict(final_artifact.media_info or {})
            current_runs = list(
                (
                    await self.db.scalars(
                        select(WorkflowStepRunModel)
                        .where(WorkflowStepRunModel.job_id == self.job.id)
                        .order_by(WorkflowStepRunModel.started_at, WorkflowStepRunModel.attempt)
                    )
                ).all()
            )
            unique: dict[str, WorkflowArtifactModel] = {}
            for run in current_runs:
                for artifact in await self.runtime.outputs(run):
                    unique[artifact.id] = artifact

            async def export_action(run):
                final_video_path = self.storage.get_path(final_artifact.relative_path)
                cover_path = self.runtime.attempt_dir(run) / "cover.png"
                await self.renderer._run_ffmpeg_command(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        "0",
                        "-i",
                        str(final_video_path),
                        "-frames:v",
                        "1",
                        "-c:v",
                        "png",
                        str(cover_path),
                    ],
                    cover_path,
                    timeout=60.0,
                )
                cover_probe = await media_probe_service.probe(cover_path)
                if not cover_probe.has_video:
                    raise ValidationException("无法从最终视频生成有效封面。")
                cover_asset = await self.gen.asset_service.save_asset_from_file(
                    cover_path,
                    file_name=f"{task.title or 'drama'}_cover.png",
                    mime_type="image/png",
                    asset_type=AssetType.IMAGE,
                    project_id=task.project_id,
                    width=cover_probe.width,
                    height=cover_probe.height,
                    metadata={
                        "drama_id": self.drama_id,
                        "episode_id": self.episode_id,
                        "source": "final_video_first_frame",
                    },
                )
                export_metadata = {
                    "schema_version": 1,
                    "title": task.title,
                    "drama_id": self.drama_id,
                    "episode_id": self.episode_id,
                    "final_video_asset_id": final_artifact.asset_id,
                    "cover_asset_id": cover_asset.id,
                    "content_mode": self.payload.get("content_mode"),
                    "template_id": self.payload.get("template_id"),
                    "total_duration_seconds": final_info.get("duration_seconds")
                    or final_info.get("video_duration"),
                    "subtitle_artifact_ids": [
                        item.id for item in subtitle_artifacts if item.kind in {"srt", "ass"}
                    ],
                }
                metadata_path = await self.runtime.write_json(
                    run, "episode_metadata.json", export_metadata
                )
                manifest = {
                    "schema_version": 1,
                    "task_id": task.id,
                    "job_id": self.job.id,
                    "drama_id": self.drama_id,
                    "episode_id": self.episode_id,
                    "configuration": self.payload,
                    "qa_before": before_findings,
                    "qa_after": after_findings,
                    "timeline": timeline,
                    "final_video_artifact_id": final_artifact.id,
                    "export": export_metadata,
                    "steps": [
                        {
                            "id": item.id,
                            "step": item.step_key,
                            "unit_key": item.unit_key,
                            "attempt": item.attempt,
                            "status": item.status,
                            "input_fingerprint": item.input_fingerprint,
                            "reused_from_id": item.reused_from_id,
                            "output": item.output_payload,
                            "error": item.error_message,
                        }
                        for item in current_runs
                        if item.id != run.id
                    ],
                    "artifacts": [
                        {
                            "id": item.id,
                            "step_run_id": item.step_run_id,
                            "kind": item.kind,
                            "path": item.relative_path,
                            "sha256": item.sha256,
                            "size_bytes": item.size_bytes,
                            "media_info": item.media_info,
                            "source": item.source,
                        }
                        for item in unique.values()
                    ],
                }
                path = await self.runtime.write_json(run, "render_manifest.json", manifest)
                return [
                    ArtifactSpec(cover_path, "cover", cover_asset.id, "generated"),
                    ArtifactSpec(metadata_path, "episode_metadata"),
                    ArtifactSpec(path, "render_manifest"),
                ], {"manifest_version": 1, **export_metadata}, None, False

            _, export_artifacts = await self.stage(
                "export",
                {"timeline": timeline, "final_artifact": final_artifact.id},
                export_action,
                dependencies=[*final_outputs, *subtitle_artifacts],
            )
            final_asset = await self.db.get(AssetModel, final_artifact.asset_id) if final_artifact.asset_id else None
            if not final_asset:
                raise ValidationException("最终视频资产不存在。")
            subtitle_ids = [item.id for item in subtitle_artifacts if item.kind in {"srt", "ass"}]
            cover_artifact = next((item for item in export_artifacts if item.kind == "cover"), None)
            metadata_artifact = next(
                (item for item in export_artifacts if item.kind == "episode_metadata"), None
            )
            manifest_artifact = next(
                (item for item in export_artifacts if item.kind == "render_manifest"), None
            )
            cover_asset = await self.db.get(AssetModel, cover_artifact.asset_id) if cover_artifact and cover_artifact.asset_id else None
            result = {
                "video_status": "ready",
                "job_id": self.job.id,
                "drama_id": self.drama_id,
                "episode_id": self.episode_id,
                "final_video_asset_id": final_asset.id,
                "final_video_path": final_artifact.relative_path,
                "final_video_url": self.storage.get_url(final_artifact.relative_path),
                "cover_asset_id": cover_asset.id if cover_asset else None,
                "cover_url": self.storage.get_url(cover_asset.file_path) if cover_asset else None,
                "subtitle_artifact_ids": subtitle_ids,
                "qa_before": before_findings,
                "qa_after": after_findings,
                "scenes_count": len(render_scenes),
                "total_duration_seconds": final_info.get("duration_seconds") or final_info.get("video_duration"),
                "render_manifest_artifact_id": manifest_artifact.id if manifest_artifact else None,
                "episode_metadata_artifact_id": metadata_artifact.id if metadata_artifact else None,
            }
            await self.runtime.assert_lease()
            task = await TaskRepository(self.db).get_by_id(task.id)
            task.status = "completed"
            task.progress_percentage = 100
            task.completed_at = datetime.now(UTC)
            task.error_message = None
            task.result_payload = {**(task.result_payload or {}), **result}
            episode = await self.db.get(DramaEpisodeModel, self.episode_id)
            if episode:
                episode.checkpoint = {
                    **(episode.checkpoint or {}),
                    "production_status": "completed",
                    "production_job_id": self.job.id,
                    "production_updated_at": datetime.now(UTC).isoformat(),
                }
            await self.db.commit()
            for event in ("video.preview_ready", "task.completed"):
                await event_broadcaster.broadcast(
                    event,
                    {**result, "task_id": task.id, "job_id": self.job.id, "status": "completed", "progress": 100, "preview_url": result["final_video_url"]},
                    task_id=task.id,
                    job_id=self.job.id,
                    lease_token=self.runtime.lease_token,
                )
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._mark_failed(exc)
            raise
