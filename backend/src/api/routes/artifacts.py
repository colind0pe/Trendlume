from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.exceptions import NotFoundException, ValidationException
from src.models.workflow import WorkflowArtifactModel, WorkflowJobModel
from src.services.workflow_runtime import safe_artifact_path

router = APIRouter(prefix="/artifacts", tags=["Workflow Artifacts"])


@router.get("/{artifact_id}/download")
async def download_workflow_artifact(
    artifact_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    artifact = await db.get(WorkflowArtifactModel, artifact_id)
    if artifact is None:
        raise NotFoundException("WorkflowArtifact", artifact_id)
    job = await db.get(WorkflowJobModel, job_id)
    if job is None or artifact.job_id != job.id or artifact.task_id != job.task_id:
        raise ValidationException("Artifact 不属于指定的 WorkflowJob。")
    path = safe_artifact_path(settings.storage_dir.resolve(), artifact.relative_path)
    if not path.is_file():
        raise NotFoundException("WorkflowArtifactFile", artifact_id)
    return FileResponse(path, filename=path.name)
