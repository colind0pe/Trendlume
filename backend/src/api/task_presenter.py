"""Shared Task API projections used by all task-facing routes."""

from src.schemas.scene import SceneResponse
from src.schemas.task import TaskDetailResponse, TaskResponse
from src.schemas.workflow import WorkflowJobResponse


def _apply_job(
    response: TaskResponse,
    task,
    job=None,
    *,
    scenes_count: int | None = None,
) -> TaskResponse:
    if job:
        response.latest_job = WorkflowJobResponse.model_validate(job)
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
