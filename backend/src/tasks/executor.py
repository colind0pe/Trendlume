from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import async_session_factory
from src.core.exceptions import ValidationException
from src.models.production_context import ProductionContextSnapshotModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel
from src.services.production_pipeline import production_pipeline_registry
from src.services.rendering_service import RenderingService
from src.tasks.job import Job


class VideoWorkflowExecutor:
    """Queue adapter for the durable, verified production pipeline."""
    def __init__(self, session_factory: async_sessionmaker = async_session_factory,
                 rendering_service_factory: Callable[[AsyncSession], RenderingService] | None = None):
        self.session_factory = session_factory
        self.rendering_service_factory = rendering_service_factory

    async def execute(self, job: Job) -> dict[str, Any]:
        async with self.session_factory() as session:
            task = await session.get(TaskModel, job.task_id)
            if task is None:
                raise ValidationException("任务不存在")
            job_record = await session.get(WorkflowJobModel, job.id)
            if job_record is None:
                raise ValidationException("WorkflowJob 不存在")
            snapshot = await session.get(
                ProductionContextSnapshotModel, job_record.production_context_snapshot_id
            )
            if snapshot is None:
                raise ValidationException("WorkflowJob 缺少生产上下文快照")
            pipeline = production_pipeline_registry.create(
                snapshot.mode,
                session,
                job,
                self.rendering_service_factory,
            )
            try:
                result = await pipeline.execute()
            except BaseException:
                if getattr(pipeline, 'owns_job', False):
                    await session.rollback()
                    await pipeline.runtime.assert_lease()
                    record = await session.get(WorkflowJobModel, job.id)
                    record.status, record.lease_token = 'failed', None
                    task = await session.get(TaskModel, job.task_id)
                    if task is not None:
                        task.production_status = 'failed'
                    await session.commit()
                raise
            if getattr(pipeline, 'owns_job', False):
                await pipeline.runtime.assert_lease()
                record = await session.get(WorkflowJobModel, job.id)
                record.status, record.lease_token = 'completed', None
                record.result, record.completed_at = result, datetime.now(UTC)
                await session.commit()
            return result

workflow_executor = VideoWorkflowExecutor()
