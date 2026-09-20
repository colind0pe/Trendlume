import asyncio
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.routes import (
    assets_router,
    events_router,
    generation_router,
    health_router,
    jobs_router,
    projects_router,
    providers_router,
    publishing_router,
    scenes_router,
    tasks_router,
    templates_router,
    trends_router,
)
from src.core.config import settings
from src.core.database import async_session_factory, verify_schema
from src.core.exceptions import AppException
from src.core.logging import install_log_filters
from src.services.provider_bootstrap import bootstrap_default_providers
from src.services.publishing_service import PublishingService
from src.services.system_asset_service import ensure_default_bgm, sync_bgm_directory_assets
from src.services.template_renderer import TemplateRenderer
from src.services.trend_scheduler import trend_scheduler
from src.tasks.manager import task_manager

install_log_filters()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info(f"🚀 Starting {settings.app_name} v{settings.app_version}...")
    missing_schema = await verify_schema()
    if missing_schema:
        message = (
            "Database schema is incomplete: "
            f"{', '.join(missing_schema)}. "
            "Run 'cd backend; .\\.venv\\Scripts\\python.exe -m alembic upgrade head' "
            "before starting Trendlume. This release does not upgrade historical schemas; "
            "if the database is not revision 001, create a new database manually."
        )
        logger.error(message)
        raise RuntimeError(message)
    async with async_session_factory() as session:
        try:
            await bootstrap_default_providers(session)
            await ensure_default_bgm(session)
            await sync_bgm_directory_assets(session)
            await session.commit()
            await PublishingService(session).migrate_legacy_credentials()
        except Exception as e:
            logger.error(f"Failed to bootstrap provider configs: {e}")
    if not await TemplateRenderer.check_available():
        logger.error(
            "Playwright Chromium is unavailable; template preview/render requests will fail explicitly."
        )
    await task_manager.start()
    await trend_scheduler.start()
    yield
    await trend_scheduler.stop()
    await task_manager.stop()
    await TemplateRenderer.close()
    logger.info("🛑 Application shutdown complete.")


def create_app() -> FastAPI:
    """FastAPI Application Factory"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS Setup
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    @app.exception_handler(AppException)
    async def app_exception_handler(request, exc: AppException):
        return exc.to_response()

    # Route Registration
    api_v1_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_v1_prefix)
    app.include_router(projects_router, prefix=api_v1_prefix)
    app.include_router(tasks_router, prefix=api_v1_prefix)
    app.include_router(scenes_router, prefix=api_v1_prefix)
    app.include_router(assets_router, prefix=api_v1_prefix)
    app.include_router(generation_router, prefix=api_v1_prefix)
    app.include_router(jobs_router, prefix=api_v1_prefix)
    app.include_router(publishing_router, prefix=api_v1_prefix)
    app.include_router(providers_router, prefix=api_v1_prefix)
    app.include_router(events_router, prefix=api_v1_prefix)
    app.include_router(templates_router, prefix=api_v1_prefix)
    app.include_router(trends_router, prefix=api_v1_prefix)

    return app


app = create_app()
