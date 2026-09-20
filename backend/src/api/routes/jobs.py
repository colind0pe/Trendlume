from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import NotFoundException, ValidationException
from src.models.task import TaskModel
from src.models.workflow import WorkflowArtifactModel, WorkflowJobModel, WorkflowStepRunModel
from src.schemas.common import APIResponse
from src.schemas.workflow import WorkflowJobResponse
from src.services.production_job_service import ProductionJobService

router = APIRouter(prefix="/workflow-jobs", tags=["Workflow Jobs"])


@router.get("/{job_id}", response_model=APIResponse[WorkflowJobResponse])
async def get_workflow_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(WorkflowJobModel, job_id)
    if job is None:
        raise NotFoundException("WorkflowJob", job_id)
    stages = list((await db.scalars(
        select(WorkflowStepRunModel).where(WorkflowStepRunModel.job_id == job_id)
        .order_by(WorkflowStepRunModel.started_at, WorkflowStepRunModel.attempt)
    )).all())
    artifacts = list((await db.scalars(
        select(WorkflowArtifactModel).where(WorkflowArtifactModel.job_id == job_id)
        .order_by(WorkflowArtifactModel.created_at)
    )).all())
    artifacts_by_run: dict[str, list[WorkflowArtifactModel]] = {}
    for artifact in artifacts:
        artifacts_by_run.setdefault(artifact.step_run_id, []).append(artifact)
    return APIResponse(data={
        **{column.name: getattr(job, column.name) for column in job.__table__.columns},
        "stages": [
            {
                **{column.name: getattr(run, column.name) for column in run.__table__.columns},
                "artifacts": artifacts_by_run.get(run.id, []),
            }
            for run in stages
        ],
        "artifacts": artifacts,
    })


@router.post("/{job_id}/retry", response_model=APIResponse[WorkflowJobResponse])
async def retry_workflow_job(job_id: str, db: AsyncSession = Depends(get_db)):
    return APIResponse(data=await ProductionJobService(db).retry(job_id))


@router.post("/{job_id}/cancel", response_model=APIResponse[WorkflowJobResponse])
async def cancel_workflow_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(WorkflowJobModel, job_id)
    if job is None:
        raise NotFoundException("WorkflowJob", job_id)
    if job.status not in {"queued", "retrying", "running"}:
        raise ValidationException("只有排队或运行中的 WorkflowJob 可以取消。")
    job.status = "cancelled"
    job.error_message = "用户取消生产"
    task = await db.get(TaskModel, job.task_id)
    if task is not None:
        task.production_status = "cancelled"
    await db.commit()
    await db.refresh(job)
    return APIResponse(data=job)


@router.get("/{job_id}/artifacts", response_model=APIResponse[list[dict]])
async def list_workflow_job_artifacts(job_id: str, db: AsyncSession = Depends(get_db)):
    if await db.get(WorkflowJobModel, job_id) is None:
        raise NotFoundException("WorkflowJob", job_id)
    artifacts = list((await db.scalars(
        select(WorkflowArtifactModel).where(WorkflowArtifactModel.job_id == job_id)
        .order_by(WorkflowArtifactModel.created_at)
    )).all())
    return APIResponse(data=[
        {column.name: getattr(item, column.name) for column in item.__table__.columns}
        for item in artifacts
    ])
