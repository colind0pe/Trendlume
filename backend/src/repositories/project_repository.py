from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.project import ProjectModel
from src.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[ProjectModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProjectModel, session)

    async def get_with_template(self, project_id: str) -> ProjectModel | None:
        stmt = (
            select(ProjectModel)
            .where(ProjectModel.id == project_id)
            .options(selectinload(ProjectModel.template))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_details(self, project_id: str) -> ProjectModel | None:
        stmt = (
            select(ProjectModel)
            .where(ProjectModel.id == project_id)
            .options(
                selectinload(ProjectModel.template),
                selectinload(ProjectModel.tasks),
                selectinload(ProjectModel.assets),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 50, offset: int = 0) -> Sequence[ProjectModel]:
        stmt = (
            select(ProjectModel)
            .options(selectinload(ProjectModel.template))
            .order_by(ProjectModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
