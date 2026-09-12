from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.task import TaskModel
from src.repositories.base import BaseRepository


class TaskRepository(BaseRepository[TaskModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(TaskModel, session)

    async def get_with_scenes(self, task_id: str) -> TaskModel | None:
        stmt = (
            select(TaskModel)
            .where(TaskModel.id == task_id)
            .options(selectinload(TaskModel.scenes))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[TaskModel]:
        stmt = select(TaskModel).options(selectinload(TaskModel.scenes))
        if project_id is not None:
            stmt = stmt.where(TaskModel.project_id == project_id)
        if status is not None:
            stmt = stmt.where(TaskModel.status == status)

        stmt = stmt.order_by(TaskModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()
