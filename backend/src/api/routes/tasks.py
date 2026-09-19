from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_commerce_preflight_service,
    get_db,
    get_generation_service,
    get_publishing_service,
    get_rendering_service,
    get_scene_service,
    get_task_service,
    request_session_factory,
)
from src.core.exceptions import ValidationException
from src.domain.enums import JobType
from src.schemas.asset import AssetResponse
from src.schemas.common import APIResponse
from src.schemas.creative_plan import CommercePreflightResponse
from src.schemas.generation import ResearchResponse
from src.schemas.publishing import (
    PublishingJobResponse,
    TaskPublishRequest,
    TaskScheduleRequest,
)
from src.schemas.scene import SceneBatchUpdate, SceneCreate, SceneResponse
from src.schemas.task import (
    TaskDetailResponse,
    TaskDuplicateRequest,
    TaskRerenderRequest,
    TaskResponse,
    TaskUpdate,
)
from src.schemas.workflow import TaskResumeRequest, WorkflowJobResponse
from src.services.commerce_preflight import CommercePreflightService
from src.services.generation_service import GenerationService
from src.services.publishing_service import PublishingService
from src.services.rendering_service import RenderingService
from src.services.scene_service import SceneService
from src.services.task_service import TaskService
from src.tasks.broadcaster import event_broadcaster
from src.tasks.manager import task_manager

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post(
    "/{task_id}/commerce-preflight",
    response_model=APIResponse[CommercePreflightResponse],
)
async def commerce_preflight(
    task_id: str,
    require_media: bool = Query(False),
    service: CommercePreflightService = Depends(get_commerce_preflight_service),
):
    return APIResponse(
        data=await service.run(task_id, require_media=require_media)
    )


async def _task_response(task, db: AsyncSession) -> TaskResponse:
    response = TaskResponse.model_validate(task)
    response.scenes_count = len(task.scenes or [])
    response.scheduled_publish = (task.input_payload or {}).get("scheduled_publish")
    factory = request_session_factory(db)
    job = await task_manager.get_latest_job(task.id, session_factory=factory, exclude_publish=True)
    if job:
        response.active_job = WorkflowJobResponse.model_validate(job)
        response.current_stage = job.current_stage
        response.resume_count = job.retry_count
        response.last_heartbeat_at = job.heartbeat_at
        response.can_resume = job.status in {"failed", "cancelled", "missed", "uncertain"}
    return response


@router.get("", response_model=APIResponse[list[TaskResponse]])
async def list_all_tasks(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks across all projects with optional status filter"""
    tasks = await service.list_tasks(status=status_filter, limit=limit, offset=offset)
    return APIResponse(data=[await _task_response(task, db) for task in tasks])


@router.get("/{task_id}", response_model=APIResponse[TaskDetailResponse])
async def get_task(
    task_id: str,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    """Get task detail including ordered scenes"""
    task = await service.get_task(task_id)
    factory = request_session_factory(db)
    latest_job = await task_manager.get_latest_job(task_id, session_factory=factory, exclude_publish=True)
    job_response = WorkflowJobResponse.model_validate(latest_job) if latest_job else None
    return APIResponse(
        data=TaskDetailResponse(
            id=task.id,
            project_id=task.project_id,
            product_id=task.product_id,
            creative_plan_id=task.creative_plan_id,
            creative_angle=task.creative_angle,
            title=task.title,
            description=task.description,
            job_type=task.job_type,
            production_mode=task.production_mode,
            status=task.status,
            progress_percentage=task.progress_percentage,
            input_payload=task.input_payload,
            result_payload=task.result_payload,
            error_message=task.error_message,
            scenes_count=len(task.scenes) if task.scenes else 0,
            scenes=[SceneResponse.model_validate(s) for s in task.scenes],
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            active_job=job_response,
            current_stage=latest_job.current_stage if latest_job else None,
            resume_count=latest_job.retry_count if latest_job else 0,
            last_heartbeat_at=latest_job.heartbeat_at if latest_job else None,
            can_resume=bool(latest_job and latest_job.status in {"failed", "cancelled", "missed", "uncertain"}),
            scheduled_publish=(task.input_payload or {}).get("scheduled_publish"),
        )
    )


@router.get("/{task_id}/research", response_model=APIResponse[ResearchResponse])
async def get_task_research(
    task_id: str,
    service: GenerationService = Depends(get_generation_service),
):
    return APIResponse(data=await service.get_task_research(task_id))


@router.post("/{task_id}/generate", response_model=APIResponse[dict])
async def trigger_task_generation(
    task_id: str,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    """Trigger asynchronous video generation workflow for a task"""
    await service.get_task(task_id)
    await db.commit()
    job = await task_manager.submit_task(task_id, session_factory=request_session_factory(db))
    return APIResponse(data=job.to_dict())


@router.post("/{task_id}/duplicate", response_model=APIResponse[TaskDetailResponse], status_code=status.HTTP_201_CREATED)
async def duplicate_task(
    task_id: str,
    payload: TaskDuplicateRequest | None = None,
    service: TaskService = Depends(get_task_service),
):
    task = await service.duplicate_task(
        task_id,
        mode=payload.mode if payload else "settings_and_script",
        title=payload.title if payload else None,
    )
    return APIResponse(data=TaskDetailResponse(
        id=task.id,
        project_id=task.project_id,
        product_id=task.product_id,
        creative_plan_id=task.creative_plan_id,
        creative_angle=task.creative_angle,
        title=task.title,
        description=task.description,
        job_type=task.job_type,
        production_mode=task.production_mode,
        status=task.status,
        progress_percentage=task.progress_percentage,
        input_payload=task.input_payload,
        result_payload=task.result_payload,
        error_message=task.error_message,
        scenes_count=len(task.scenes or []),
        scenes=[SceneResponse.model_validate(scene) for scene in task.scenes or []],
        started_at=task.started_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        scheduled_publish=(task.input_payload or {}).get("scheduled_publish"),
    ))


@router.post("/{task_id}/rerender", response_model=APIResponse[dict])
async def rerender_task(
    task_id: str,
    payload: TaskRerenderRequest | None = None,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    existing = await task_manager.get_latest_job(
        task_id, job_type=JobType.FULL_PIPELINE.value, session_factory=request_session_factory(db)
    )
    if existing and existing.status not in {"completed", "failed", "cancelled", "missed", "uncertain"}:
        raise ValidationException("任务正在执行，完成或取消后才能重新渲染。")
    task = await service.prepare_rerender(
        task_id,
        template_id=payload.template_id if payload else None,
        template_params=payload.template_params if payload else None,
        bgm_enabled=payload.bgm_enabled if payload else None,
        bgm_asset_id=payload.bgm_asset_id if payload else None,
        bgm_volume=payload.bgm_volume if payload else None,
    )
    await db.commit()
    job = await task_manager.submit_task(
        task_id,
        params={"rerender": True},
        checkpoint={"stage": "render", "progress": 0},
        session_factory=request_session_factory(db),
    )
    return APIResponse(data={"task_id": task.id, "job": job.to_dict()})


@router.post("/{task_id}/compose", response_model=APIResponse[AssetResponse])
async def compose_task_final_video(
    task_id: str,
    rendering_service: RenderingService = Depends(get_rendering_service),
):
    """Compose all scene clips into the final single MP4 video asset"""
    result = await task_manager.run_inline(task_id, {"single_step": "composition", "force_step": "composition"}, session_factory=request_session_factory(rendering_service.session))
    from src.models.asset import AssetModel
    final_asset = await rendering_service.session.get(AssetModel, result["final_video_asset_id"])
    return APIResponse(data=AssetResponse.model_validate(final_asset))


@router.post("/{task_id}/publish", response_model=APIResponse[PublishingJobResponse])
async def publish_task_video(
    task_id: str,
    payload: TaskPublishRequest = TaskPublishRequest(),
    pub_service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    """Prepare Douyin publishing job and enqueue into existing TaskManager"""
    job = await pub_service.prepare_task_publishing(
        task_id=task_id,
        account_id=payload.account_id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        cover_asset_id=payload.cover_asset_id,
    )
    await db.commit()
    # Submit to local TaskManager
    await task_manager.submit_task(
        task_id=task_id,
        job_type=JobType.PUBLISH.value,
        params={"publishing_job_id": job.id, "task_id": task_id},
        session_factory=request_session_factory(db),
    )
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/{task_id}/schedule", response_model=APIResponse[PublishingJobResponse])
async def schedule_task_video(
    task_id: str,
    payload: TaskScheduleRequest,
    pub_service: PublishingService = Depends(get_publishing_service),
    db: AsyncSession = Depends(get_db),
):
    """Create a durable scheduled publishing job."""
    job = await pub_service.prepare_task_publishing(
        task_id=task_id,
        account_id=payload.account_id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        cover_asset_id=payload.cover_asset_id,
        scheduled_at=payload.scheduled_at,
    )
    await db.commit()
    await task_manager.submit_task(
        task_id=task_id,
        job_type=JobType.PUBLISH.value,
        params={"publishing_job_id": job.id, "task_id": task_id},
        available_at=payload.scheduled_at,
        scheduled_at=payload.scheduled_at,
        session_factory=request_session_factory(db),
    )
    return APIResponse(data=PublishingJobResponse.model_validate(job))


@router.post("/{task_id}/cancel", response_model=APIResponse[bool])
async def cancel_task_generation(
    task_id: str,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    """Cancel in-flight or queued video generation task"""
    await service.get_task(task_id)
    result = await task_manager.cancel_task(task_id, session_factory=request_session_factory(db))
    return APIResponse(data=result)


@router.post("/{task_id}/scheduled-publish/cancel", response_model=APIResponse[bool])
async def cancel_scheduled_publish(
    task_id: str,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    """Cancel the publish automatically attached to a generated task."""
    task = await service.get_task(task_id)
    payload = dict(task.input_payload or {})
    stored_config = payload.get("scheduled_publish")
    config = dict(stored_config) if isinstance(stored_config, dict) else stored_config
    if not isinstance(config, dict):
        raise ValidationException("该任务没有配置完成后自动发布。")
    if config.get("status") in {"published", "failed", "cancelled", "missed"}:
        raise ValidationException("该自动发布任务已经结束，无法取消。")

    publishing_job_id = config.get("publishing_job_id")
    if publishing_job_id:
        cancelled = await task_manager.cancel_publishing_workflow(
            publishing_job_id,
            session_factory=request_session_factory(db),
        )
        if not cancelled:
            raise ValidationException("自动发布工作流不存在或已经结束。")

    config.update({"status": "cancelled", "error_message": None})
    payload["scheduled_publish"] = config
    task.input_payload = payload
    await db.commit()
    return APIResponse(data=True)


@router.post("/{task_id}/retry", response_model=APIResponse[dict])
async def retry_task_generation(
    task_id: str,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed or cancelled task generation"""
    await service.get_task(task_id)
    await db.commit()
    job = await task_manager.retry_task(task_id, session_factory=request_session_factory(db))
    return APIResponse(data=job.to_dict())


@router.post("/{task_id}/resume", response_model=APIResponse[dict])
async def resume_task_generation(
    task_id: str,
    payload: TaskResumeRequest | None = None,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    await service.get_task(task_id)
    job = await task_manager.resume_task(task_id, payload.job_id if payload else None, session_factory=request_session_factory(db))
    return APIResponse(data=job.to_dict())


@router.get("/{task_id}/jobs", response_model=APIResponse[list[WorkflowJobResponse]])
async def list_task_workflow_jobs(task_id: str, service: TaskService = Depends(get_task_service), db: AsyncSession = Depends(get_db)):
    await service.get_task(task_id)
    jobs = await task_manager.list_jobs(task_id, session_factory=request_session_factory(db))
    return APIResponse(data=[WorkflowJobResponse.model_validate(job) for job in jobs])


@router.get("/{task_id}/events")
async def task_events_stream(
    task_id: str,
    request: Request,
    last_event_id: int = Header(default=0, alias="Last-Event-ID"),
    last_event_id_query: int | None = Query(default=None, alias="last_event_id", ge=0),
):
    """Server-Sent Events (SSE) real-time stream specifically for this task_id"""
    client_queue = event_broadcaster.subscribe(task_id=task_id)
    replay_messages = await event_broadcaster.replay(
        task_id, last_event_id_query if last_event_id_query is not None else last_event_id
    )
    return StreamingResponse(
        event_broadcaster.event_generator(
            client_queue, task_id=task_id, replay_messages=replay_messages, request=request
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/{task_id}", response_model=APIResponse[TaskDetailResponse])
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    task = await service.update_task(task_id, payload)
    factory = request_session_factory(db)
    latest_job = await task_manager.get_latest_job(task_id, session_factory=factory, exclude_publish=True)
    job_response = WorkflowJobResponse.model_validate(latest_job) if latest_job else None
    return APIResponse(
        data=TaskDetailResponse(
            id=task.id,
            project_id=task.project_id,
            product_id=task.product_id,
            creative_plan_id=task.creative_plan_id,
            creative_angle=task.creative_angle,
            title=task.title,
            description=task.description,
            job_type=task.job_type,
            production_mode=task.production_mode,
            status=task.status,
            progress_percentage=task.progress_percentage,
            input_payload=task.input_payload,
            result_payload=task.result_payload,
            error_message=task.error_message,
            scenes_count=len(task.scenes) if task.scenes else 0,
            scenes=[SceneResponse.model_validate(s) for s in task.scenes],
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            active_job=job_response,
            current_stage=latest_job.current_stage if latest_job else None,
            resume_count=latest_job.retry_count if latest_job else 0,
            last_heartbeat_at=latest_job.heartbeat_at if latest_job else None,
            can_resume=bool(latest_job and latest_job.status in {"failed", "cancelled", "missed", "uncertain"}),
            scheduled_publish=(task.input_payload or {}).get("scheduled_publish"),
        )
    )


@router.delete("/{task_id}", response_model=APIResponse[bool])
async def delete_task(
    task_id: str,
    service: TaskService = Depends(get_task_service),
):
    await task_manager.cancel_task(task_id)
    result = await service.delete_task(task_id)
    return APIResponse(data=result)


# Scenes Sub-resource under Task (1:N with Task)
@router.get("/{task_id}/scenes", response_model=APIResponse[list[SceneResponse]])
async def list_task_scenes(
    task_id: str,
    scene_service: SceneService = Depends(get_scene_service),
):
    scenes = await scene_service.list_scenes_by_task(task_id)
    return APIResponse(data=[SceneResponse.model_validate(s) for s in scenes])


@router.post(
    "/{task_id}/scenes",
    response_model=APIResponse[SceneResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_task_scene(
    task_id: str,
    payload: SceneCreate,
    scene_service: SceneService = Depends(get_scene_service),
):
    scene = await scene_service.create_scene(task_id, payload)
    return APIResponse(data=SceneResponse.model_validate(scene))


@router.put("/{task_id}/scenes", response_model=APIResponse[list[SceneResponse]])
async def batch_update_task_scenes(
    task_id: str,
    payload: SceneBatchUpdate,
    scene_service: SceneService = Depends(get_scene_service),
):
    scenes = await scene_service.replace_task_scenes(task_id, payload.scenes)
    return APIResponse(data=[SceneResponse.model_validate(s) for s in scenes])
