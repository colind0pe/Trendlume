from src.api.routes.assets import router as assets_router
from src.api.routes.drama import router as drama_router
from src.api.routes.events import router as events_router
from src.api.routes.generation import router as generation_router
from src.api.routes.health import router as health_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.products import router as products_router
from src.api.routes.projects import router as projects_router
from src.api.routes.providers import router as providers_router
from src.api.routes.publishing import router as publishing_router
from src.api.routes.scenes import router as scenes_router
from src.api.routes.tasks import router as tasks_router
from src.api.routes.templates import router as templates_router
from src.api.routes.trends import router as trends_router

__all__ = [
    "health_router",
    "projects_router",
    "products_router",
    "tasks_router",
    "scenes_router",
    "assets_router",
    "generation_router",
    "jobs_router",
    "drama_router",
    "publishing_router",
    "providers_router",
    "events_router",
    "templates_router",
    "trends_router",
]
