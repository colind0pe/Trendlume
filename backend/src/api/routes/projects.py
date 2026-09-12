from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    get_asset_service,
    get_db,
    get_project_service,
    get_task_service,
    get_template_service,
    request_session_factory,
)
from src.domain.enums import JobType
from src.schemas.asset import AssetResponse
from src.schemas.common import APIResponse
from src.schemas.project import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
)
from src.schemas.task import TaskCreate, TaskResponse
from src.schemas.template import ProjectTemplateResponse, ProjectTemplateUpdate
from src.schemas.workflow import WorkflowJobResponse
from src.services.asset_service import AssetService
from src.services.project_service import ProjectService
from src.services.system_asset_service import sync_bgm_directory_assets
from src.services.task_service import TaskService
from src.services.template_service import ProjectTemplateService
from src.tasks.manager import task_manager

router = APIRouter(prefix="/projects", tags=["Projects"])


def _task_response(task, job=None) -> TaskResponse:
    """Build a task DTO with optional durable-job progress."""
    response = TaskResponse.model_validate(task)
    response.scenes_count = len(task.scenes or [])
    response.scheduled_publish = (task.input_payload or {}).get("scheduled_publish")
    if job:
        response.active_job = WorkflowJobResponse.model_validate(job)
        response.current_stage = job.current_stage
        response.resume_count = job.retry_count
        response.last_heartbeat_at = job.heartbeat_at
        response.can_resume = job.status in {"failed", "cancelled", "missed", "uncertain"}
    return response


@router.post("", response_model=APIResponse[ProjectResponse], status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
):
    project = await service.create_project(payload)
    return APIResponse(data=ProjectResponse.model_validate(project))


@router.get("", response_model=APIResponse[list[ProjectResponse]])
async def list_projects(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: ProjectService = Depends(get_project_service),
):
    projects = await service.list_projects(limit=limit, offset=offset)
    return APIResponse(data=[ProjectResponse.model_validate(p) for p in projects])


@router.get("/{project_id}/bgm", response_model=APIResponse[list[AssetResponse]])
async def list_project_bgm(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    asset_service: AssetService = Depends(get_asset_service),
):
    """Return legal project BGM assets and the read-only system catalog."""
    await project_service.get_project(project_id)
    if await sync_bgm_directory_assets(asset_service.session, asset_service.storage):
        await asset_service.session.commit()
    assets = await asset_service.list_project_bgm(project_id)
    return APIResponse(data=[AssetResponse.model_validate(asset) for asset in assets])


@router.get("/{project_id}", response_model=APIResponse[ProjectDetailResponse])
async def get_project_detail(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
):
    project = await service.get_project_detail(project_id)
    return APIResponse(data=ProjectDetailResponse.model_validate(project))


@router.patch("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    service: ProjectService = Depends(get_project_service),
):
    project = await service.update_project(project_id, payload)
    return APIResponse(data=ProjectResponse.model_validate(project))


@router.delete("/{project_id}", response_model=APIResponse[bool])
async def delete_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
):
    result = await service.delete_project(project_id)
    return APIResponse(data=result)


# Template Sub-resource (1:1 with Project)
@router.get("/{project_id}/template", response_model=APIResponse[ProjectTemplateResponse])
async def get_project_template(
    project_id: str,
    template_service: ProjectTemplateService = Depends(get_template_service),
):
    template = await template_service.get_template_by_project(project_id)
    return APIResponse(data=ProjectTemplateResponse.model_validate(template))


@router.put("/{project_id}/template", response_model=APIResponse[ProjectTemplateResponse])
async def update_project_template(
    project_id: str,
    payload: ProjectTemplateUpdate,
    template_service: ProjectTemplateService = Depends(get_template_service),
):
    template = await template_service.update_template(project_id, payload)
    return APIResponse(data=ProjectTemplateResponse.model_validate(template))


# Tasks Sub-resource (1:N with Project)
@router.get("/{project_id}/tasks", response_model=APIResponse[list[TaskResponse]])
async def list_project_tasks(
    project_id: str,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    task_service: TaskService = Depends(get_task_service),
    db: AsyncSession = Depends(get_db),
):
    tasks = await task_service.list_tasks(
        project_id=project_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    factory = request_session_factory(db)
    responses = []
    for task in tasks:
        job = await task_manager.get_latest_job(
            task.id,
            job_type=JobType.FULL_PIPELINE.value,
            session_factory=factory,
        )
        if not job:
            job = await task_manager.get_latest_job(task.id, session_factory=factory)
        responses.append(_task_response(task, job))
    return APIResponse(data=responses)


@router.post(
    "/{project_id}/tasks",
    response_model=APIResponse[TaskResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task(
    project_id: str,
    payload: TaskCreate,
    task_service: TaskService = Depends(get_task_service),
):
    task = await task_service.create_task(project_id, payload)
    response = TaskResponse.model_validate(task)
    response.scheduled_publish = (task.input_payload or {}).get("scheduled_publish")
    return APIResponse(data=response)
