from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.scene import SceneModel
from src.repositories.base import BaseRepository


class SceneRepository(BaseRepository[SceneModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(SceneModel, session)

    async def list_by_task_id(self, task_id: str) -> Sequence[SceneModel]:
        stmt = (
            select(SceneModel)
            .where(SceneModel.task_id == task_id)
            .order_by(SceneModel.sequence_index.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_by_task_id(self, task_id: str) -> int:
        stmt = delete(SceneModel).where(SceneModel.task_id == task_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
