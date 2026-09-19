"""Read-only stage snapshots and integrity-checked artifact delivery."""
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.core.config import settings
from src.domain.production_workflows import get_production_workflow
from src.models.asset import AssetModel
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.models.workflow import (
    WorkflowArtifactModel,
    WorkflowJobModel,
    WorkflowStepArtifactModel,
    WorkflowStepRunModel,
)
from src.schemas.common import APIResponse
from src.schemas.workflow import (
    WorkflowArtifactResponse,
    WorkflowJobResponse,
    WorkflowSnapshotResponse,
    WorkflowStageSummaryResponse,
    WorkflowStepRetryRequest,
    WorkflowStepRunResponse,
)
from src.services.workflow_runtime import (
    SUCCESS_STATUSES,
    safe_artifact_path,
    validate_artifact,
)
from src.tasks.manager import task_manager

router = APIRouter(tags=["Workflow"])


async def require_task(db, task_id):
    if await db.get(TaskModel, task_id) is None:
        raise HTTPException(404, "Task not found")


async def serialize_runs(db, runs):
    ids = [run.id for run in runs]
    links = (await db.execute(select(WorkflowStepArtifactModel.step_run_id, WorkflowArtifactModel).join(
        WorkflowArtifactModel, WorkflowArtifactModel.id == WorkflowStepArtifactModel.artifact_id
    ).where(WorkflowStepArtifactModel.step_run_id.in_(ids), WorkflowStepArtifactModel.role.in_(("output", "reuse"))))).all() if ids else []
    grouped = {}
    checks = {}
    for run_id, artifact in links:
        grouped.setdefault(run_id, []).append(artifact)
    results = []
    for run in runs:
        dto = WorkflowStepRunResponse.model_validate(run)
        artifacts = grouped.get(run.id, [])
        dto.artifacts = [WorkflowArtifactResponse.model_validate(a) for a in artifacts]
        for artifact in artifacts:
            if artifact.id not in checks:
                try:
                    checks[artifact.id] = await validate_artifact(settings.storage_dir, artifact)
                except (ValueError, OSError):
                    checks[artifact.id] = (False, "制品路径无效")
            ok, reason = checks[artifact.id]
            if not ok:
                dto.validity, dto.invalid_reason = "corrupt", reason
        if run.status in SUCCESS_STATUSES and not artifacts and run.status != "skipped" and not (run.output_payload or {}).get("_skipped"):
            dto.validity, dto.invalid_reason = "corrupt", "阶段没有可校验输出"
        results.append(dto)
    return results


@router.get("/tasks/{task_id}/workflow", response_model=APIResponse[WorkflowSnapshotResponse])
async def get_workflow(task_id: str, db: AsyncSession = Depends(get_db)):
    await require_task(db, task_id)
    task = await db.get(TaskModel, task_id)
    workflow = get_production_workflow(getattr(task, "production_mode", None))
    runs = list((await db.scalars(select(WorkflowStepRunModel).where(WorkflowStepRunModel.task_id == task_id).order_by(WorkflowStepRunModel.started_at, WorkflowStepRunModel.attempt))).all())
    history = await serialize_runs(db, runs)
    scene_ids = set((await db.scalars(select(SceneModel.id).where(SceneModel.task_id == task_id))).all())
    stages = []
    for stage in workflow.stages:
        key = stage.key
        stage_history = [run for run in history if run.step_key == key]
        latest = {run.unit_key: run for run in stage_history if not run.unit_key or run.unit_key in scene_ids or run.unit_key == 'final'}
        units = list(latest.values())
        statuses = {run.status for run in units}
        state = next((s for s in ("running", "failed", "interrupted", "cancelled", "waiting", "completed_with_warning") if s in statuses), None)
        state = state or ("reused" if statuses == {"reused"} else "skipped" if statuses == {"skipped"} else "completed" if units else "waiting")
        validity = "corrupt" if any(r.validity == "corrupt" for r in units) else "stale" if any(r.validity == "stale" for r in units) else "valid"
        stages.append(WorkflowStageSummaryResponse(step_key=key, label=stage.label, status=state, validity=validity,
            duration_ms=sum(r.duration_ms or 0 for r in stage_history), retry_count=sum(1 for i, r in enumerate(stage_history) if r.status != 'reused' and any(p.unit_key == r.unit_key and p.status in {'failed', 'interrupted'} for p in stage_history[:i])), units=units, history=stage_history))
    return APIResponse(data=WorkflowSnapshotResponse(task_id=task_id, stages=stages))


@router.get("/jobs/{job_id}/steps", response_model=APIResponse[list[WorkflowStepRunResponse]])
async def get_steps(job_id: str, db: AsyncSession = Depends(get_db)):
    if await db.get(WorkflowJobModel, job_id) is None:
        raise HTTPException(404, "Workflow job not found")
    runs = (await db.scalars(select(WorkflowStepRunModel).where(WorkflowStepRunModel.job_id == job_id).order_by(WorkflowStepRunModel.started_at))).all()
    return APIResponse(data=await serialize_runs(db, runs))


@router.post("/tasks/{task_id}/steps/{step_key}/retry", response_model=APIResponse[WorkflowJobResponse])
async def retry_step(task_id: str, step_key: str, payload: WorkflowStepRetryRequest | None = None, db: AsyncSession = Depends(get_db)):
    await require_task(db, task_id)
    task = await db.get(TaskModel, task_id)
    workflow = get_production_workflow(getattr(task, "production_mode", None))
    if not workflow.has_stage(step_key):
        raise HTTPException(422, "Unknown workflow stage")
    unit = payload.unit_key if payload else None
    if unit:
        scene = await db.get(SceneModel, unit)
        if step_key not in workflow.unit_stage_keys or scene is None or scene.task_id != task_id:
            raise HTTPException(422, "Execution unit does not belong to this task and stage")
    @asynccontextmanager
    async def factory():
        yield db
    await db.commit()
    job = await task_manager.submit_task(task_id, params={"force_step": step_key, "force_unit": unit}, session_factory=factory)
    model = await task_manager.get_job(job.id, session_factory=factory)
    return APIResponse(data=WorkflowJobResponse.model_validate(model))


@router.get("/tasks/{task_id}/artifacts", response_model=APIResponse[list[WorkflowArtifactResponse]])
async def get_artifacts(task_id: str, db: AsyncSession = Depends(get_db)):
    await require_task(db, task_id)
    rows = (await db.scalars(select(WorkflowArtifactModel).where(WorkflowArtifactModel.task_id == task_id).order_by(WorkflowArtifactModel.created_at))).all()
    return APIResponse(data=[WorkflowArtifactResponse.model_validate(a) for a in rows])


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str, task_id: str | None = None, db: AsyncSession = Depends(get_db)):
    artifact = await db.get(WorkflowArtifactModel, artifact_id)
    if artifact is None or (task_id is not None and task_id != artifact.task_id):
        raise HTTPException(404, "Artifact not found")
    await require_task(db, artifact.task_id)
    producer = await db.get(WorkflowStepRunModel, artifact.step_run_id)
    if producer is None or producer.task_id != artifact.task_id:
        raise HTTPException(409, "Artifact ownership mismatch")
    if artifact.asset_id:
        task = await db.get(TaskModel, artifact.task_id)
        asset = await db.get(AssetModel, artifact.asset_id)
        if asset is None or task is None or asset.project_id != task.project_id:
            raise HTTPException(409, "Artifact asset ownership mismatch")
    ok, reason = await validate_artifact(settings.storage_dir, artifact)
    if not ok:
        raise HTTPException(409, f"制品校验失败：{reason}")
    path = safe_artifact_path(settings.storage_dir, artifact.relative_path)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff"})
