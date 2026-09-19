from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.services.asset_service import AssetService
from src.services.commerce_planning_service import CommercePlanningService
from src.services.commerce_preflight import CommercePreflightService
from src.services.drama_production_service import DramaProductionService
from src.services.generation_service import GenerationService
from src.services.product_service import ProductService
from src.services.project_service import ProjectService
from src.services.provider_manager import ProviderManager
from src.services.publishing_service import PublishingService
from src.services.rendering_service import RenderingService
from src.services.scene_service import SceneService
from src.services.task_service import TaskService
from src.services.template_service import ProjectTemplateService
from src.services.trend_service import TrendService


def request_session_factory(db: AsyncSession):
    @asynccontextmanager
    async def factory():
        yield db

    return factory


def get_provider_manager(session: AsyncSession = Depends(get_db)) -> ProviderManager:
    return ProviderManager(session)


def get_project_service(session: AsyncSession = Depends(get_db)) -> ProjectService:
    return ProjectService(session)


def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    return ProductService(session)


def get_commerce_planning_service(
    session: AsyncSession = Depends(get_db),
) -> CommercePlanningService:
    return CommercePlanningService(session)


def get_commerce_preflight_service(
    session: AsyncSession = Depends(get_db),
) -> CommercePreflightService:
    return CommercePreflightService(session)


def get_drama_service(session: AsyncSession = Depends(get_db)) -> DramaProductionService:
    return DramaProductionService(session)


def get_template_service(session: AsyncSession = Depends(get_db)) -> ProjectTemplateService:
    return ProjectTemplateService(session)


def get_task_service(session: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(session)


def get_scene_service(session: AsyncSession = Depends(get_db)) -> SceneService:
    return SceneService(session)


def get_asset_service(session: AsyncSession = Depends(get_db)) -> AssetService:
    return AssetService(session)


def get_generation_service(session: AsyncSession = Depends(get_db)) -> GenerationService:
    return GenerationService(session)


def get_rendering_service(session: AsyncSession = Depends(get_db)) -> RenderingService:
    return RenderingService(session)


def get_publishing_service(session: AsyncSession = Depends(get_db)) -> PublishingService:
    return PublishingService(session)


def get_trend_service(session: AsyncSession = Depends(get_db)) -> TrendService:
    return TrendService(session)
