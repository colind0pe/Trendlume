from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.template import ProjectTemplateModel
from src.repositories.base import BaseRepository


class ProjectTemplateRepository(BaseRepository[ProjectTemplateModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProjectTemplateModel, session)

    async def get_by_project_id(self, project_id: str) -> ProjectTemplateModel | None:
        stmt = select(ProjectTemplateModel).where(ProjectTemplateModel.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
