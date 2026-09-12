import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import Base
from src.core.exceptions import ValidationException
from src.services.provider_bootstrap import bootstrap_default_providers
from src.services.provider_manager import ProviderManager


@pytest.mark.asyncio
async def test_allow_delete_all_providers_and_no_forced_rebootstrap(tmp_path):
    db_file = tmp_path / "empty_test.db"
    db_url = "sqlite+aiosqlite:///" + str(db_file).replace("\\", "/")

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Initialize tables & First-time bootstrap
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        assert await bootstrap_default_providers(session) is True
        manager = ProviderManager(session)

        for provider_type in ("llm", "image"):
            providers = await manager.list_providers(provider_type=provider_type)
            assert providers
            for provider in providers:
                assert await manager.delete_provider(provider.id) is True
            assert await manager.list_providers(provider_type=provider_type) == []
            assert await manager.repo.get_default(provider_type) is None

        with pytest.raises(ValidationException, match="未配置大语言模型"):
            await manager.get_llm()
        with pytest.raises(ValidationException, match="未配置分镜画面生成服务"):
            await manager.get_image()

    await engine.dispose()

    # ----------------------------------------------------------------------
    # 5. RESTART SIMULATION: Ensure no default providers are recreated
    # ----------------------------------------------------------------------
    engine_restarted = create_async_engine(db_url, echo=False)
    session_factory_restarted = async_sessionmaker(engine_restarted, expire_on_commit=False, class_=AsyncSession)

    async with session_factory_restarted() as session_after_restart:
        rebootstrapped = await bootstrap_default_providers(session_after_restart)
        assert rebootstrapped is False

        manager_restarted = ProviderManager(session_after_restart)
        for provider_type in ("llm", "image"):
            assert await manager_restarted.list_providers(provider_type=provider_type) == []

    await engine_restarted.dispose()
