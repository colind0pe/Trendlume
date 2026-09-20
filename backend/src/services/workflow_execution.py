"""Transaction fences shared by workers and interactive production edits."""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, TrendlumeException
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel, WorkflowStepRunModel
from src.services.workflow_runtime import LeaseLostError

WorkflowLeaseLost = LeaseLostError


@dataclass(frozen=True)
class WorkflowExecutionContext:
    job_id: str
    lease_token: str

    async def fence(self, session: AsyncSession) -> None:
        with session.no_autoflush:
            result = await session.execute(
                update(WorkflowJobModel).where(
                    WorkflowJobModel.id == self.job_id,
                    WorkflowJobModel.lease_token == self.lease_token,
                    WorkflowJobModel.status == "running",
                ).values(heartbeat_at=datetime.now(UTC).replace(tzinfo=None))
                .execution_options(synchronize_session=False, autoflush=False)
            )
        if not self.lease_token or result.rowcount != 1:
            await session.rollback()
            raise WorkflowLeaseLost("Workflow execution lease is no longer current")


async def lock_task(session: AsyncSession, task_id: str) -> None:
    with session.no_autoflush:
        result = await session.execute(update(TaskModel).where(TaskModel.id == task_id)
            .values(updated_at=TaskModel.updated_at)
            .execution_options(synchronize_session=False, autoflush=False))
    if result.rowcount != 1:
        raise NotFoundException("Task", task_id)


async def assert_task_editable(session: AsyncSession, task_id: str) -> None:
    await lock_task(session, task_id)
    active = await session.scalar(select(WorkflowJobModel.id).where(
        WorkflowJobModel.task_id == task_id,
        WorkflowJobModel.job_type != "publish",
        WorkflowJobModel.status.in_(["pending", "queued", "running", "retrying"]),
    ).limit(1))
    if active:
        raise TrendlumeException("任务正在执行，请先取消任务后再修改生产输入。", "TASK_BUSY", 409)


async def mark_steps_stale(session: AsyncSession, task_id: str, steps: set[str], reason: str,
                           unit_key: str | None = None) -> None:
    query = update(WorkflowStepRunModel).where(WorkflowStepRunModel.task_id == task_id,
        WorkflowStepRunModel.step_key.in_(steps), WorkflowStepRunModel.validity == "valid")
    if unit_key is not None:
        query = query.where(WorkflowStepRunModel.unit_key.in_([unit_key, ""]))
    await session.execute(query.values(validity="stale", invalid_reason=reason)
                          .execution_options(synchronize_session=False))


async def mark_manual_storyboard(session: AsyncSession, task_id: str) -> None:
    task = await session.get(TaskModel, task_id)
    if task:
        task.generation_settings = {
            **(task.generation_settings or {}),
            "manual_storyboard_version": uuid.uuid4().hex,
        }


async def interrupt_steps(session: AsyncSession, job_id: str, status: str = "interrupted") -> None:
    await session.execute(update(WorkflowStepRunModel).where(
        WorkflowStepRunModel.job_id == job_id, WorkflowStepRunModel.status == "running",
    ).values(status=status, completed_at=datetime.now(UTC).replace(tzinfo=None))
      .execution_options(synchronize_session=False))
