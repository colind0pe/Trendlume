from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db


def request_session_factory(db: AsyncSession):
    @asynccontextmanager
    async def factory():
        yield db

    return factory


def _factory(module, name, session):
    imported = __import__(module, fromlist=[name])
    return getattr(imported, name)(session)


def get_project_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.project_service", "ProjectService", session)


def get_task_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.task_service", "TaskService", session)


def get_provider_manager(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.provider_manager", "ProviderManager", session)


def get_template_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.template_service", "ProjectTemplateService", session)


def get_scene_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.scene_service", "SceneService", session)


def get_asset_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.asset_service", "AssetService", session)


def get_generation_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.generation_service", "GenerationService", session)


def get_rendering_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.rendering_service", "RenderingService", session)


def get_publishing_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.publishing_service", "PublishingService", session)


def get_trend_service(session: AsyncSession = Depends(get_db)):
    return _factory("src.services.trend_service", "TrendService", session)
