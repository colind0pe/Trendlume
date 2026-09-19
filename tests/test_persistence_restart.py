from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import Base
from src.core.security import SecretCipher
from src.schemas.provider import ProviderConfigUpdate
from src.services.provider_bootstrap import bootstrap_default_providers
from src.services.provider_manager import ProviderManager


@pytest.mark.asyncio
async def test_restart_persistence_and_priority(tmp_path: Path):
    """
    Verify that:
    1. First start bootstraps defaults into SQLite.
    2. User customizes a provider (e.g. changes model, base_url, api_key).
    3. User sets custom provider as default.
    4. Process restarts (simulated new session & bootstrap call).
    5. User changes in SQLite are preserved and NOT overwritten by .env defaults!
    """
    db_file = tmp_path / "persistence_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Initialize Tables & First Start
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        bootstrapped = await bootstrap_default_providers(session)
        assert bootstrapped is True
        manager = ProviderManager(session)

        # 2. Modify DeepSeek config in SQLite
        deepseek_p = await manager.repo.get_by_name("llm", "deepseek")
        assert deepseek_p is not None

        await manager.update_provider(
            deepseek_p.id,
            ProviderConfigUpdate(
                display_name="DeepSeek Custom Production",
                config={"base_url": "https://custom-proxy.deepseek.com/v1", "model": "deepseek-reasoner"},
                credentials={"api_key": "sk-user-custom-secret-key-999"},
            ),
        )

        # 3. Configure the bootstrapped Claude preset and make it the default LLM
        claude_p = await manager.repo.get_by_name("llm", "claude")
        assert claude_p is not None
        claude_p = await manager.update_provider(
            claude_p.id,
            ProviderConfigUpdate(
                display_name="Anthropic Claude Sonnet 5",
                enabled=True,
                is_default=True,
                config={"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-5"},
                credentials={"api_key": "sk-ant-user-secret-888"},
            ),
        )
        assert claude_p.is_default is True

    # Dispose connection to simulate complete backend server shutdown
    await engine.dispose()

    # --------------------------------------------------------------------------
    # 4. RESTART SIMULATION: New Engine, New Session, App Startup Lifespan
    # --------------------------------------------------------------------------
    engine_restarted = create_async_engine(db_url, echo=False)
    session_factory_restarted = async_sessionmaker(engine_restarted, expire_on_commit=False, class_=AsyncSession)

    async with session_factory_restarted() as session_after_restart:
        # Startup lifespan runs bootstrap again
        second_bootstrap = await bootstrap_default_providers(session_after_restart)
        assert second_bootstrap is False  # Must NOT overwrite existing DB!

        manager_restarted = ProviderManager(session_after_restart)

        # Verify Claude is STILL the default LLM
        default_llm = await manager_restarted.repo.get_default("llm")
        assert default_llm is not None
        assert default_llm.provider_name == "claude"
        assert default_llm.display_name == "Anthropic Claude Sonnet 5"

        # Verify DeepSeek modifications are STILL preserved
        deepseek_restarted = await manager_restarted.repo.get_by_name("llm", "deepseek")
        assert deepseek_restarted is not None
        assert deepseek_restarted.display_name == "DeepSeek Custom Production"
        assert deepseek_restarted.config["base_url"] == "https://custom-proxy.deepseek.com/v1"
        assert deepseek_restarted.config["model"] == "deepseek-reasoner"

        # Verify decrypted credential is still accurate
        cipher = SecretCipher()
        decrypted = cipher.decrypt_dict(deepseek_restarted.credentials_encrypted)
        assert decrypted["api_key"] == "sk-user-custom-secret-key-999"

    await engine_restarted.dispose()
