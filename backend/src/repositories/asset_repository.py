from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import AssetType, is_bgm_storage_path
from src.models.asset import AssetModel
from src.models.project import ProjectAssetBindingModel
from src.repositories.base import BaseRepository


class AssetRepository(BaseRepository[AssetModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(AssetModel, session)

    async def list_by_project(
        self,
        project_id: str | None = None,
        asset_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AssetModel]:
        stmt = select(AssetModel)
        if project_id is not None:
            stmt = stmt.join(ProjectAssetBindingModel).where(
                ProjectAssetBindingModel.project_id == project_id
            )
        if asset_type is not None:
            stmt = stmt.where(AssetModel.asset_type == asset_type)

        stmt = stmt.order_by(AssetModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_project_bgm(self, project_id: str) -> Sequence[AssetModel]:
        """List legal project BGM plus the read-only system BGM catalog."""
        bound_ids = select(ProjectAssetBindingModel.asset_id).where(
            ProjectAssetBindingModel.project_id == project_id
        )
        stmt = select(AssetModel).where(
            AssetModel.asset_type == AssetType.BGM.value,
            (AssetModel.id.in_(bound_ids))
            | (AssetModel.metadata_json["scope"].as_string() == "system"),
        ).order_by(AssetModel.created_at.desc())
        result = await self.session.execute(stmt)
        return [
            asset
            for asset in result.scalars().all()
            if is_bgm_storage_path(asset.file_path)
            and (
                asset.id in set((await self.session.scalars(bound_ids)).all())
                or (asset.metadata_json or {}).get("scope") == "system"
            )
        ]
