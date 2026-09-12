from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.database import async_session_factory
from src.models.workflow import WorkflowJobModel
from src.services.durable_pipeline import DurableVideoPipeline
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
            pipeline = DurableVideoPipeline(session, job, self.rendering_service_factory)
            try:
                result = await pipeline.execute()
            except BaseException:
                if getattr(pipeline, 'owns_job', False):
                    await session.rollback()
                    await pipeline.runtime.assert_lease()
                    record = await session.get(WorkflowJobModel, job.id)
                    record.status, record.lease_token = 'failed', None
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
