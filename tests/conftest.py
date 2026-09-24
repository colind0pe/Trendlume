# Imports below intentionally follow the local path bootstrap.
# ruff: noqa: E402
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

# Add workspace root and backend to sys.path
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tests.mocks import (
    MockImageProvider,
    MockLLMProvider,
    MockSearchProvider,
    MockTTSProvider,
    MockVideoProvider,
)

from src.api.app import create_app
from src.core.database import Base, get_db
from src.providers.registry import provider_registry
from src.services.template_renderer import TemplateRenderer


@pytest.fixture(autouse=True)
def setup_test_providers(monkeypatch):
    monkeypatch.setattr(provider_registry, "_search_provider", MockSearchProvider())
    monkeypatch.setattr(provider_registry, "_llm_provider", MockLLMProvider())
    monkeypatch.setattr(provider_registry, "_tts_provider", MockTTSProvider())
    monkeypatch.setattr(provider_registry, "_image_provider", MockImageProvider())
    monkeypatch.setattr(provider_registry, "_video_provider", MockVideoProvider())


@pytest_asyncio.fixture(autouse=True)
async def close_template_renderer() -> AsyncGenerator[None, None]:
    """Do not carry Playwright objects across per-test asyncio event loops."""
    try:
        yield
    finally:
        await TemplateRenderer.close()


@pytest_asyncio.fixture(scope="function")
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    # A unique shared-memory database supports independent worker sessions
    # without leaking locks or connections into another test process.
    database_url = (
        f"sqlite+aiosqlite:///file:trendlume_test_{uuid4().hex}"
        "?mode=memory&cache=shared&uri=true"
    )
    engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=AsyncAdaptedQueuePool,
        connect_args={"timeout": 30},
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with async_session() as session:
            from src.services.provider_bootstrap import bootstrap_default_providers
            await bootstrap_default_providers(session)
            yield session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(test_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
