from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_task_service
from src.api.routes.projects import _task
from src.core.database import get_db
from src.models.workflow import WorkflowJobModel
from src.schemas.common import APIResponse
from src.schemas.task import TaskDetailResponse, TaskResponse, TaskUpdate
from src.schemas.workflow import WorkflowJobResponse
from src.services.production_context import ProductionContextCompiler
from src.services.production_job_service import ProductionJobService
from src.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", response_model=APIResponse[list[TaskResponse]])
async def list_tasks(
    project_id: str | None = Query(None),
    editorial_status: str | None = Query(None),
    production_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: TaskService = Depends(get_task_service),
):
    tasks = await service.list_tasks(
        project_id,
        editorial_status=editorial_status,
        production_status=production_status,
        limit=limit,
        offset=offset,
    )
    latest: dict[str, WorkflowJobModel] = {}
    if tasks:
        jobs = (await service.session.scalars(
            select(WorkflowJobModel)
            .where(
                WorkflowJobModel.task_id.in_([task.id for task in tasks]),
                WorkflowJobModel.job_type == "full_pipeline",
            )
            .order_by(WorkflowJobModel.created_at.desc())
        )).all()
        for job in jobs:
            latest.setdefault(job.task_id, job)
    return APIResponse(data=[{**_task(task), "latest_job": latest.get(task.id)} for task in tasks])


@router.get("/{task_id}", response_model=APIResponse[TaskDetailResponse])
async def get_task(task_id: str, service: TaskService = Depends(get_task_service)):
    task = await service.get_task(task_id)
    return APIResponse(data={**_task(task), "scenes": task.scenes})


@router.patch("/{task_id}", response_model=APIResponse[TaskDetailResponse])
async def update_task(
    task_id: str, payload: TaskUpdate, service: TaskService = Depends(get_task_service)
):
    task = await service.update_task(task_id, payload)
    return APIResponse(data={**_task(task), "scenes": task.scenes})


@router.post("/{task_id}/approve", response_model=APIResponse[TaskDetailResponse])
async def approve_task(task_id: str, service: TaskService = Depends(get_task_service)):
    task = await service.approve(task_id)
    return APIResponse(data={**_task(task), "scenes": task.scenes})


@router.get("/{task_id}/readiness", response_model=APIResponse[dict])
async def get_task_readiness(task_id: str, db: AsyncSession = Depends(get_db)):
    return APIResponse(data=await ProductionContextCompiler(db).readiness(task_id))


@router.delete("/{task_id}", response_model=APIResponse[bool])
async def delete_task(task_id: str, service: TaskService = Depends(get_task_service)):
    return APIResponse(data=await service.delete_task(task_id))


@router.post("/{task_id}/duplicate", response_model=APIResponse[TaskDetailResponse])
async def duplicate_task(task_id: str, service: TaskService = Depends(get_task_service)):
    task = await service.duplicate_task(task_id)
    return APIResponse(data={**_task(task), "scenes": task.scenes})


@router.get("/{task_id}/jobs", response_model=APIResponse[list[WorkflowJobResponse]])
async def list_task_jobs(task_id: str, db: AsyncSession = Depends(get_db)):
    jobs = (
        await db.scalars(
            select(WorkflowJobModel)
            .where(
                WorkflowJobModel.task_id == task_id,
                WorkflowJobModel.job_type == "full_pipeline",
            )
            .order_by(WorkflowJobModel.created_at.desc())
        )
    ).all()
    return APIResponse(data=list(jobs))


@router.post("/{task_id}/jobs", response_model=APIResponse[WorkflowJobResponse])
async def produce_task(task_id: str, db: AsyncSession = Depends(get_db)):
    return APIResponse(data=await ProductionJobService(db).create(task_id))
