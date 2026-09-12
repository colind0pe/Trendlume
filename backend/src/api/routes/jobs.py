from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.schemas.common import APIResponse
from src.schemas.workflow import WorkflowJobResponse
from src.tasks.manager import task_manager

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=APIResponse[WorkflowJobResponse])
async def get_workflow_job(job_id: str, db: AsyncSession = Depends(get_db)):
    @asynccontextmanager
    async def factory():
        yield db

    job = await task_manager.get_job(job_id, session_factory=factory)
    if not job:
        raise HTTPException(status_code=404, detail=f"WorkflowJob not found: {job_id}")
    return APIResponse(data=WorkflowJobResponse.model_validate(job))
