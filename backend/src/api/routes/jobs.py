from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import NotFoundException
from src.models.workflow import WorkflowJobModel
from src.schemas.common import APIResponse
from src.schemas.workflow import WorkflowJobResponse
from src.services.production_job_service import ProductionJobService

router = APIRouter(prefix="/workflow-jobs", tags=["Workflow Jobs"])


@router.get("/{job_id}", response_model=APIResponse[WorkflowJobResponse])
async def get_workflow_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(WorkflowJobModel, job_id)
    if job is None:
        raise NotFoundException("WorkflowJob", job_id)
    return APIResponse(data=job)


@router.post("/{job_id}/retry", response_model=APIResponse[WorkflowJobResponse])
async def retry_workflow_job(job_id: str, db: AsyncSession = Depends(get_db)):
    return APIResponse(data=await ProductionJobService(db).retry(job_id))
