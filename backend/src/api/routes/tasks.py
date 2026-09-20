from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_task_service
from src.api.routes.projects import _task
from src.core.database import get_db
from src.schemas.common import APIResponse
from src.schemas.task import TaskDetailResponse, TaskUpdate
from src.schemas.workflow import WorkflowJobResponse
from src.services.production_job_service import ProductionJobService
from src.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])


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


@router.post("/{task_id}/jobs", response_model=APIResponse[WorkflowJobResponse])
@router.post("/{task_id}/produce", response_model=APIResponse[WorkflowJobResponse])
async def produce_task(task_id: str, db: AsyncSession = Depends(get_db)):
    return APIResponse(data=await ProductionJobService(db).create(task_id))
