import uuid
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.content_modes import is_content_mode_supported, resolve_content_mode
from src.domain.enums import AccountStatus, AssetType, PlatformType, TaskStatus
from src.models.asset import AssetModel
from src.models.publishing import SocialAccountModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.repositories.project_repository import ProjectRepository
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.schemas.task import ScheduledPublishConfig, TaskCreate, TaskUpdate
from src.services.provider_manager import ProviderManager
from src.services.system_asset_service import is_system_asset
from src.services.template_catalog import template_catalog
from src.services.workflow_execution import assert_task_editable, mark_steps_stale
from src.services.workflow_service import workflow_service


def _coerce_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "off"}:
            return False
        if normalized in {"true", "1", "yes", "on"}:
            return True
    return bool(value)


class TaskService:
    """Application service for Video Tasks"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.task_repo = TaskRepository(session)
        self.scene_repo = SceneRepository(session)
        self.project_repo = ProjectRepository(session)

    async def _normalize_scheduled_publish(
        self,
        config: ScheduledPublishConfig | dict | None,
    ) -> dict | None:
        """Validate and persist a creation-time schedule as normalized JSON."""
        if config is None:
            return None

        try:
            schedule = (
                config
                if isinstance(config, ScheduledPublishConfig)
                else ScheduledPublishConfig.model_validate(config)
            )
        except Exception as exc:
            raise ValidationException("定时发布配置不完整，请选择发布账号、时间和时区。") from exc

        account = await self.session.get(SocialAccountModel, schedule.account_id)
        if not account:
            raise ValidationException("选择的发布账号不存在。")
        if account.platform != PlatformType.DOUYIN.value:
            raise ValidationException("完成后自动发布目前仅支持抖音账号。")
        if account.status != AccountStatus.ACTIVE.value or not account.credential_id:
            raise ValidationException("选择的抖音账号尚未准备好，请先完成扫码登录并检查账号状态。")

        timezone_name = schedule.timezone.strip()
        if not timezone_name:
            raise ValidationException("请选择有效的时区。")
        scheduled_at = schedule.scheduled_at
        if scheduled_at.tzinfo is None:
            # Browser clients submit an offset-aware ISO timestamp, so this
            # path does not need a local tzdata installation (important on
            # Windows).  Only naive API input needs an IANA timezone lookup.
            try:
                timezone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValidationException("无法识别所选时区，请刷新页面后重试。") from exc
            scheduled_at = scheduled_at.replace(tzinfo=timezone)
        scheduled_at_utc = scheduled_at.astimezone(UTC)
        if scheduled_at_utc <= datetime.now(UTC) + timedelta(minutes=1):
            raise ValidationException("计划发布时间至少需要晚于当前时间 1 分钟。")

        return {
            "enabled": True,
            "account_id": schedule.account_id,
            "scheduled_at": scheduled_at_utc.isoformat(),
            "timezone": timezone_name,
            "status": "pending",
            "publishing_job_id": None,
            "error_message": None,
        }

    async def build_task(
        self, project_id: str, data: TaskCreate
    ) -> TaskModel:
        """Validate and build a task without committing it."""
        # Ensure project exists
        project = await self.project_repo.get_with_template(project_id)
        if not project:
            raise NotFoundException("Project", project_id)

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        payload = dict(data.input_payload or {})
        requested_template_id = payload.get("template_id", data.template_id)
        if requested_template_id == "default_portrait" and "template_id" not in payload:
            project_template = getattr(project, "template", None)
            requested_template_id = getattr(project_template, "template_id", None) or requested_template_id
        template = template_catalog.get(requested_template_id)
        if not template:
            raise NotFoundException("Template", requested_template_id)

        legacy_visual_mode = payload.get("visual_mode", data.visual_mode)
        content_mode = resolve_content_mode(
            payload.get("content_mode", data.content_mode),
            template_type=template["template_type"],
            visual_mode=legacy_visual_mode,
        )
        if not is_content_mode_supported(content_mode, template["template_type"]):
            raise ValidationException(
                f"模板 {requested_template_id} 不支持内容模式 {content_mode}"
            )
        # Content mode is the single source of truth.  Keep visual_mode only
        # as a backwards-compatible alias for older clients and tasks.
        legacy_visual_mode = "video" if content_mode == "generated_video" else "image"

        source_asset_id = payload.get("source_asset_id", data.source_asset_id)
        if content_mode == "uploaded_asset":
            if not source_asset_id:
                raise ValidationException("上传素材模式必须选择 source_asset_id。")
            source_asset = await self.session.get(AssetModel, source_asset_id)
            if not source_asset or source_asset.project_id != project_id:
                raise ValidationException("素材不存在或不属于当前项目。")
            if source_asset.asset_type not in {AssetType.IMAGE.value, AssetType.VIDEO.value}:
                raise ValidationException("上传素材模式只支持图片或视频素材。")

        bgm_enabled = _coerce_bool(
            payload.get("bgm_enabled"), data.bgm_enabled
        )
        bgm_volume = payload.get("bgm_volume", data.bgm_volume)
        try:
            bgm_volume = float(bgm_volume)
        except (TypeError, ValueError) as exc:
            raise ValidationException("BGM 音量必须是 0.0 到 0.5 之间的数字。") from exc
        if not 0.0 <= bgm_volume <= 0.5:
            raise ValidationException("BGM 音量必须在 0.0 到 0.5 之间。")

        bgm_asset_id = payload.get("bgm_asset_id", data.bgm_asset_id)
        if bgm_enabled and not bgm_asset_id:
            # ProjectService assigns the Demo system asset for new projects;
            # older projects may intentionally have no default BGM.
            bgm_asset_id = project.bgm_asset_id
        if not bgm_enabled:
            bgm_asset_id = None
        if bgm_asset_id:
            bgm_asset = await self.session.get(AssetModel, bgm_asset_id)
            if not bgm_asset or (
                bgm_asset.project_id != project_id and not is_system_asset(bgm_asset)
            ):
                raise ValidationException("背景音乐不存在或不属于当前项目。")
            if bgm_asset.asset_type not in {AssetType.AUDIO.value, AssetType.BGM.value}:
                raise ValidationException("背景音乐必须是音频或 BGM 素材。")

        image_workflow_id = payload.get(
            "image_workflow_id", data.image_workflow_id
        )
        video_workflow_id = payload.get(
            "video_workflow_id", data.video_workflow_id
        )
        try:
            image_workflow_snapshot = workflow_service.get_workflow_snapshot(
                image_workflow_id, expected_type="image"
            )
            video_workflow_snapshot = workflow_service.get_workflow_snapshot(
                video_workflow_id, expected_type="video"
            )
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

        enable_research = _coerce_bool(
            payload.get("enable_research"), data.enable_research
        )
        search_provider_id = payload.get(
            "search_provider_id", data.search_provider_id
        )
        research_max_queries = payload.get(
            "research_max_queries", data.research_max_queries
        )
        research_max_results = payload.get(
            "research_max_results", data.research_max_results
        )
        try:
            research_max_queries = int(research_max_queries)
            research_max_results = int(research_max_results)
        except (TypeError, ValueError) as exc:
            raise ValidationException("研究查询数量和单查询结果数量必须是数字。") from exc
        if not 1 <= research_max_queries <= 3 or not 1 <= research_max_results <= 5:
            raise ValidationException("研究查询数量最多 3 个，每个查询最多返回 5 条结果。")

        target_scene_count = payload.get("target_scene_count", data.target_scene_count)
        try:
            target_scene_count = int(target_scene_count)
        except (TypeError, ValueError) as exc:
            raise ValidationException("目标分镜数量必须是数字。") from exc
        if not 8 <= target_scene_count <= 20:
            raise ValidationException("目标分镜数量必须在 8 到 20 段之间。")

        schedule_input = payload.get("scheduled_publish")
        if schedule_input is None and data.scheduled_publish is not None:
            schedule_input = data.scheduled_publish
        scheduled_publish = await self._normalize_scheduled_publish(
            schedule_input,
        )

        project_template = getattr(project, "template", None)
        # Snapshot the complete parameter chain so historical tasks are
        # unaffected by later project/template edits:
        # scene (applied at render time) > task > project > template defaults.
        project_params = dict(template.get("default_params") or {})
        project_params.update(getattr(project_template, "params", None) or {})
        project_params.update(data.template_params or {})
        effective_speed = payload.get(
            "speed", payload.get("voice_speed", data.voice_speed)
        )
        input_payload = {
            **payload,
            "visual_mode": legacy_visual_mode,
            "content_mode": content_mode,
            "target_scene_count": target_scene_count,
            "template_id": requested_template_id,
            "template_version": template["version"],
            "template_params": project_params,
            "source_asset_id": source_asset_id,
            "bgm_asset_id": bgm_asset_id,
            "bgm_enabled": bool(bgm_enabled),
            "bgm_volume": round(bgm_volume, 3),
            "voice_id": payload.get("voice_id") or data.voice_id or await ProviderManager(self.session).get_default_tts_voice(),
            "speed": effective_speed,
            "voice_speed": effective_speed,
            "enable_research": bool(enable_research),
            "search_provider_id": search_provider_id,
            "material_provider_id": payload.get(
                "material_provider_id", data.material_provider_id
            ),
            "research_max_queries": research_max_queries,
            "research_max_results": research_max_results,
            "image_workflow_id": image_workflow_id,
            "video_workflow_id": video_workflow_id,
            "image_workflow_snapshot": image_workflow_snapshot,
            "video_workflow_snapshot": video_workflow_snapshot,
        }
        if scheduled_publish is None:
            input_payload.pop("scheduled_publish", None)
        else:
            input_payload["scheduled_publish"] = scheduled_publish
        if project_template and getattr(project_template, "custom_css", ""):
            input_payload["custom_css"] = project_template.custom_css
        task = TaskModel(
            id=task_id,
            project_id=project_id,
            title=data.title,
            description=data.description,
            job_type=data.job_type.value,
            status=TaskStatus.DRAFT.value,
            progress_percentage=0,
            input_payload=input_payload,
        )
        return task

    async def create_task(self, project_id: str, data: TaskCreate) -> TaskModel:
        task = await self.build_task(project_id, data)
        task = await self.task_repo.create(task)
        await self.session.commit()
        return task

    async def get_task(self, task_id: str) -> TaskModel:
        task = await self.task_repo.get_with_scenes(task_id)
        if not task:
            raise NotFoundException("Task", task_id)
        return task

    async def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[TaskModel]:
        return await self.task_repo.list_tasks(
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_task(self, task_id: str, data: TaskUpdate) -> TaskModel:
        await assert_task_editable(self.session, task_id)
        task = await self.get_task(task_id)
        old_payload = task.input_payload or {}
        new_payload = None
        changed = set()
        if data.input_payload is not None:
            def is_internal(key: str) -> bool:
                return key.startswith("workflow_") or key.startswith("manual_") or key.startswith("_")

            new_payload = {key: value for key, value in data.input_payload.items() if not is_internal(key)}
            new_payload.update({key: value for key, value in old_payload.items() if is_internal(key)})
            changed = {key for key in old_payload.keys() | new_payload.keys()
                       if old_payload.get(key) != new_payload.get(key)}
        steps = set()
        if changed & {"bgm_enabled", "bgm_asset_id", "bgm_volume"}:
            steps.update({"composition", "export"})
        if changed & {"voice_id", "speed", "voice_speed"}:
            steps.update({"planning", "voice", "subtitles", "composition", "export"})
        if changed & {"template_id", "template_version", "template_params", "custom_css"}:
            steps.update({"planning", "composition", "export"})
        if changed & {"content_mode", "visual_mode", "source_asset_id", "image_workflow_id", "video_workflow_id"}:
            steps.update({"planning", "assets", "composition", "export"})
        handled = {"bgm_enabled", "bgm_asset_id", "bgm_volume", "voice_id", "speed", "voice_speed",
                   "template_id", "template_version", "template_params", "custom_css", "content_mode",
                   "visual_mode", "source_asset_id", "image_workflow_id", "video_workflow_id"}
        if changed - handled or (data.title is not None and data.title != task.title):
            steps.update({"topic", "research", "planning", "script", "storyboard", "assets", "voice", "subtitles", "composition", "export"})
        if steps:
            await mark_steps_stale(self.session, task_id, steps, "任务输入已修改")
        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.status is not None:
            task.status = data.status.value
        if data.input_payload is not None:
            task.input_payload = new_payload
        if data.result_payload is not None:
            task.result_payload = data.result_payload
        if data.error_message is not None:
            task.error_message = data.error_message

        await self.task_repo.update(task)
        await self.session.commit()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        res = await self.task_repo.delete_by_id(task.id)
        await self.session.commit()
        return res

    async def duplicate_task(
        self, task_id: str, *, mode: str = "settings_and_script", title: str | None = None
    ) -> TaskModel:
        source = await self.get_task(task_id)
        if mode not in {"settings_only", "settings_and_script"}:
            raise ValidationException("复制模式必须为 settings_only 或 settings_and_script。")
        clone = TaskModel(
            id=f"task_{uuid.uuid4().hex[:12]}",
            project_id=source.project_id,
            title=title or f"{source.title} - 副本",
            description=source.description,
            job_type=source.job_type,
            status=TaskStatus.DRAFT.value,
            progress_percentage=0,
            input_payload={
                key: value
                for key, value in deepcopy(source.input_payload or {}).items()
                if key != "scheduled_publish"
            },
            result_payload=None,
            error_message=None,
        )
        clone = await self.task_repo.create(clone)
        if mode == "settings_and_script":
            for source_scene in source.scenes or []:
                await self.scene_repo.create(
                    SceneModel(
                        id=f"scene_{uuid.uuid4().hex[:12]}",
                        task_id=clone.id,
                        sequence_index=source_scene.sequence_index,
                        narration_text=source_scene.narration_text,
                        visual_prompt=source_scene.visual_prompt,
                        duration_seconds=source_scene.duration_seconds,
                        layout_params=deepcopy(source_scene.layout_params or {}),
                        audio_asset_id=None,
                        media_asset_id=None,
                        rendered_segment_asset_id=None,
                    )
                )
        await self.session.commit()
        return await self.get_task(clone.id)

    async def prepare_rerender(
        self,
        task_id: str,
        *,
        template_id: str | None = None,
        template_params: dict | None = None,
        bgm_enabled: bool | None = None,
        bgm_asset_id: str | None = None,
        bgm_volume: float | None = None,
    ) -> TaskModel:
        await assert_task_editable(self.session, task_id)
        task = await self.get_task(task_id)
        payload = deepcopy(task.input_payload or {})
        old_template_id = payload.get("template_id", "default_portrait")
        selected_id = template_id or payload.get("template_id", "default_portrait")
        item = template_catalog.get(selected_id)
        if not item:
            raise NotFoundException("Template", selected_id)
        content_mode = resolve_content_mode(
            payload.get("content_mode"),
            template_type=item["template_type"],
            visual_mode=payload.get("visual_mode"),
        )
        if not is_content_mode_supported(content_mode, item["template_type"]):
            raise ValidationException(f"模板 {selected_id} 不支持内容模式 {content_mode}")
        project = await self.project_repo.get_by_id(task.project_id)
        project_aspect = (project.aspect_ratio if project else None) or "9:16"
        template_aspect = item.get("aspect_ratio") or "9:16"
        if template_aspect != project_aspect:
            raise ValidationException(
                f"模板 {selected_id} 画幅 ({template_aspect}) 与项目画幅 ({project_aspect}) 不匹配"
            )
        payload["template_id"] = selected_id
        payload["template_version"] = item["version"]
        payload["template_params"] = {
            **(item.get("default_params") or {}),
            **(payload.get("template_params") or {}),
            **(template_params or {}),
        }

        if bgm_enabled is not None:
            payload["bgm_enabled"] = bgm_enabled
            if not bgm_enabled:
                payload["bgm_asset_id"] = None
        if bgm_asset_id is not None and bgm_enabled is not False:
            payload["bgm_asset_id"] = bgm_asset_id
            payload["bgm_enabled"] = True
        if bgm_volume is not None:
            payload["bgm_volume"] = bgm_volume

        effective_bgm_enabled = _coerce_bool(payload.get("bgm_enabled"), False)
        effective_bgm_id = payload.get("bgm_asset_id")
        if effective_bgm_enabled and not effective_bgm_id:
            effective_bgm_id = project.bgm_asset_id if project else None
            payload["bgm_asset_id"] = effective_bgm_id
        try:
            effective_bgm_volume = float(payload.get("bgm_volume", 0.20))
        except (TypeError, ValueError) as exc:
            raise ValidationException("BGM 音量必须是 0.0 到 0.5 之间的数字。") from exc
        if not 0.0 <= effective_bgm_volume <= 0.5:
            raise ValidationException("BGM 音量必须在 0.0 到 0.5 之间。")
        if effective_bgm_id:
            bgm_asset = await self.session.get(AssetModel, effective_bgm_id)
            if not bgm_asset or (
                bgm_asset.project_id != task.project_id and not is_system_asset(bgm_asset)
            ):
                raise ValidationException("背景音乐不存在或不属于当前项目。")
            if bgm_asset.asset_type not in {AssetType.AUDIO.value, AssetType.BGM.value}:
                raise ValidationException("背景音乐必须是音频或 BGM 素材。")
        task.input_payload = payload
        previous_result = task.result_payload or {}
        previous_id = previous_result.get("final_video_asset_id")
        history = list(previous_result.get("final_video_versions") or [])
        if previous_id and not any(item.get("asset_id") == previous_id for item in history if isinstance(item, dict)):
            history.append(
                {
                    "asset_id": previous_id,
                    "url": previous_result.get("final_video_url"),
                    "path": previous_result.get("final_video_path"),
                    "template_id": old_template_id,
                }
            )
        task.result_payload = {
            **previous_result,
            "final_video_versions": history,
            "previous_final_video_asset_id": previous_id,
        }
        task.result_payload.pop("final_video_asset_id", None)
        task.result_payload.pop("final_video_url", None)
        task.result_payload.pop("final_video_path", None)
        task.status = TaskStatus.PENDING.value
        task.progress_percentage = 0
        task.error_message = None
        task.completed_at = None
        for scene in task.scenes or []:
            scene.rendered_segment_asset_id = None
        await self.session.commit()
        return await self.get_task(task_id)
