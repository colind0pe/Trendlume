from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository providing basic async CRUD operations"""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id_: str) -> ModelType | None:
        stmt = select(self.model).where(self.model.id == id_)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, instance: ModelType) -> ModelType:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: ModelType) -> ModelType:
        await self.session.flush()
        return instance

    async def delete_by_id(self, id_: str) -> bool:
        instance = await self.get_by_id(id_)
        if instance is not None:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False
