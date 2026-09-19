"""Shared Task API projections used by all task-facing routes."""

from src.domain.production_workflows import get_production_workflow
from src.schemas.scene import SceneResponse
from src.schemas.task import TaskDetailResponse, TaskResponse
from src.schemas.workflow import WorkflowJobResponse


def _stage_label(production_mode: str, stage_key: str | None) -> str | None:
    if not stage_key:
        return None
    workflow = get_production_workflow(production_mode)
    stage = next((item for item in workflow.stages if item.key == stage_key), None)
    return stage.label if stage else stage_key


def _apply_job(
    response: TaskResponse,
    task,
    job=None,
    *,
    scenes_count: int | None = None,
) -> TaskResponse:
    response.scenes_count = len(task.scenes or []) if scenes_count is None else scenes_count
    response.scheduled_publish = (task.input_payload or {}).get("scheduled_publish")
    if job:
        response.active_job = WorkflowJobResponse.model_validate(job)
        response.current_stage = job.current_stage
        response.current_stage_label = _stage_label(task.production_mode, job.current_stage)
        response.resume_count = job.retry_count
        response.last_heartbeat_at = job.heartbeat_at
        response.can_resume = job.status in {"failed", "cancelled", "missed", "uncertain"}
    return response


def task_response(task, job=None, *, scenes_count: int | None = None) -> TaskResponse:
    return _apply_job(
        TaskResponse.model_validate(task),
        task,
        job,
        scenes_count=scenes_count,
    )


def task_detail_response(task, job=None) -> TaskDetailResponse:
    base = task_response(task, job)
    return TaskDetailResponse(
        **base.model_dump(),
        scenes=[SceneResponse.model_validate(scene) for scene in task.scenes or []],
    )
