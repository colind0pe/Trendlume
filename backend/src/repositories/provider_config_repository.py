from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.provider_config import ProviderConfigModel
from src.repositories.base import BaseRepository


class ProviderConfigRepository(BaseRepository[ProviderConfigModel]):
    """Repository handling persistence, queries, and defaults for ProviderConfigModel"""

    def __init__(self, session: AsyncSession):
        super().__init__(ProviderConfigModel, session)

    async def list_by_type(self, provider_type: str | None = None) -> Sequence[ProviderConfigModel]:
        """List provider configurations, excluding internal system records"""
        stmt = select(ProviderConfigModel).where(ProviderConfigModel.provider_type != "system")
        if provider_type:
            stmt = stmt.where(ProviderConfigModel.provider_type == provider_type)
        stmt = stmt.order_by(
            ProviderConfigModel.provider_type,
            ProviderConfigModel.is_default.desc(),
            ProviderConfigModel.created_at.asc(),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_default(self, provider_type: str) -> ProviderConfigModel | None:
        """Get current default enabled provider config for a specific category"""
        stmt = (
            select(ProviderConfigModel)
            .where(
                ProviderConfigModel.provider_type == provider_type,
                ProviderConfigModel.is_default.is_(True),
                ProviderConfigModel.enabled.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        res = result.scalar_one_or_none()
        if res:
            return res

        # Fallback: if no default is explicitly marked default, return the first enabled one
        stmt_fallback = (
            select(ProviderConfigModel)
            .where(
                ProviderConfigModel.provider_type == provider_type,
                ProviderConfigModel.enabled.is_(True),
            )
            .order_by(ProviderConfigModel.created_at.asc())
            .limit(1)
        )
        res_fb = await self.session.execute(stmt_fallback)
        return res_fb.scalar_one_or_none()

    async def get_by_name(
        self, provider_type: str, provider_name: str
    ) -> ProviderConfigModel | None:
        """Find a provider config by its provider_type and provider_name"""
        stmt = select(ProviderConfigModel).where(
            ProviderConfigModel.provider_type == provider_type,
            ProviderConfigModel.provider_name == provider_name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_default(self, provider_id: str, provider_type: str) -> ProviderConfigModel | None:
        """Set a provider as the default for its type, clearing default flag on other providers of same type"""
        # 1. Unset default for all providers of this type
        await self.session.execute(
            update(ProviderConfigModel)
            .where(ProviderConfigModel.provider_type == provider_type)
            .values(is_default=False)
        )
        # 2. Set default and enable for target provider
        await self.session.execute(
            update(ProviderConfigModel)
            .where(ProviderConfigModel.id == provider_id)
            .values(is_default=True, enabled=True)
        )
        await self.session.flush()
        return await self.get_by_id(provider_id)

    async def toggle_enabled(
        self, provider_id: str, enabled: bool | None = None
    ) -> ProviderConfigModel | None:
        """Toggle or set the enabled flag for a provider config"""
        target = await self.get_by_id(provider_id)
        if target:
            target.enabled = enabled if enabled is not None else not target.enabled
            # If disabling the default provider, clear is_default
            if not target.enabled and target.is_default:
                target.is_default = False
            await self.session.flush()
        return target
