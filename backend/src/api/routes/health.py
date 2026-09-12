from datetime import UTC, datetime

from fastapi import APIRouter

from src.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Health check endpoint providing system status and environment metadata"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "timestamp": datetime.now(UTC).isoformat(),
        "storage": {
            "data_dir": str(settings.data_dir),
            "storage_dir": str(settings.storage_dir),
        },
    }
