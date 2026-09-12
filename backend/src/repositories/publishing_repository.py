from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.publishing import CredentialModel, PublishingJobModel, SocialAccountModel
from src.repositories.base import BaseRepository


class CredentialRepository(BaseRepository[CredentialModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(CredentialModel, session)


class SocialAccountRepository(BaseRepository[SocialAccountModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(SocialAccountModel, session)

    async def list_by_platform(self, platform: str | None = None) -> Sequence[SocialAccountModel]:
        stmt = select(SocialAccountModel)
        if platform:
            stmt = stmt.where(SocialAccountModel.platform == platform)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class PublishingJobRepository(BaseRepository[PublishingJobModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(PublishingJobModel, session)

    async def list_jobs(
        self,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[PublishingJobModel]:
        stmt = select(PublishingJobModel)
        if project_id is not None:
            stmt = stmt.where(PublishingJobModel.project_id == project_id)
        if status is not None:
            stmt = stmt.where(PublishingJobModel.status == status)

        stmt = stmt.order_by(PublishingJobModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()
