from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.dependencies import get_db, get_trend_service, request_session_factory
from src.api.task_presenter import task_response
from src.core.exceptions import ValidationException
from src.schemas.common import APIResponse
from src.schemas.trend import (
    TrendFeedResponse,
    TrendPreferencesResponse,
    TrendPreferencesUpdate,
    TrendProposalActionResponse,
    TrendProposalApproveRequest,
    TrendProposalCreate,
    TrendProposalRejectRequest,
    TrendProposalResponse,
    TrendProposalUpdate,
    TrendRefreshRequest,
    TrendRunResponse,
    TrendSourceCatalogResponse,
    TrendSubscriptionCreate,
    TrendSubscriptionResponse,
    TrendSubscriptionUpdate,
)
from src.services.trend_scheduler import TrendScheduler, trend_scheduler
from src.services.trend_service import TrendService

router = APIRouter(prefix="/trends", tags=["Trends"])


def _request_scheduler(db: AsyncSession) -> TrendScheduler:
    """Bind request-scoped subscription operations to the request database."""

    # Subscription runs can outlive the request transaction long enough for a
    # lease heartbeat to fire.  A fresh session per scheduler operation keeps
    # that heartbeat independent from FastAPI's request-scoped AsyncSession.
    bind = db.bind
    session_factory = (
        async_sessionmaker(bind, expire_on_commit=False, class_=AsyncSession)
        if bind is not None
        else request_session_factory(db)
    )
    return TrendScheduler(
        session_factory,
        registry=trend_scheduler.registry,
        lease_seconds=trend_scheduler.lease_seconds,
        source_timeout_seconds=trend_scheduler.source_timeout_seconds,
        poll_interval_seconds=trend_scheduler.poll_interval_seconds,
    )


@router.get("", response_model=APIResponse[TrendFeedResponse])
async def list_trends(
    project_id: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    freshness: Literal["15m", "1h", "6h", "24h", "all"] = Query(default="24h"),
    service: TrendService = Depends(get_trend_service),
):
    feed = await service.list_feed(
        project_id=project_id,
        platform=platform,
        freshness=freshness,
    )
    return APIResponse(data=feed)


@router.get(
    "/sources",
    response_model=APIResponse[list[TrendSourceCatalogResponse]],
)
async def list_trend_sources():
    """Describe registered source configuration; latest health comes from TrendRun."""

    adapters = trend_scheduler.registry.resolve([], [])
    return APIResponse(
        data=[
            TrendSourceCatalogResponse(
                source_key=str(getattr(adapter, "source_key", "unknown")),
                adapter_name=str(getattr(adapter, "adapter_name", adapter.__class__.__name__)),
                platform=str(getattr(adapter, "platform", "unknown")),
                platform_label=str(
                    getattr(adapter, "label", getattr(adapter, "platform", "unknown"))
                ),
                # These flags describe configured endpoints only. They are not
                # a health check; the latest TrendRun source status is the
                # authoritative result of the most recent request.
                primary_available=bool(getattr(adapter, "primary_url", None)),
                fallback_available=bool(getattr(adapter, "fallback_available", False)),
            )
            for adapter in adapters
        ]
    )


@router.post(
    "/refresh",
    response_model=APIResponse[TrendRunResponse],
)
async def refresh_trends(
    payload: TrendRefreshRequest | None = None,
    service: TrendService = Depends(get_trend_service),
):
    """Fetch the configured public sources and persist one real TrendRun."""

    request = payload or TrendRefreshRequest()
    registry = trend_scheduler.registry
    registered_keys = {key.casefold() for key in registry.registered_keys()}
    requested_keys = {
        str(key).strip().casefold()
        for key in request.source_keys
        if str(key).strip() and str(key).strip().casefold() != "all"
    }
    unknown_keys = sorted(requested_keys - registered_keys)
    if unknown_keys:
        raise ValidationException(f"不支持的趋势来源：{', '.join(unknown_keys)}。")

    adapters = registry.resolve(request.source_keys, request.platforms)
    requested_platforms = {
        str(platform).strip().casefold()
        for platform in request.platforms
        if str(platform).strip() and str(platform).strip().casefold() != "all"
    }
    known_platforms = registry.registered_platforms()
    unknown_platforms = sorted(requested_platforms - known_platforms)
    if unknown_platforms:
        raise ValidationException(f"不支持的趋势平台：{', '.join(unknown_platforms)}。")

    return APIResponse(
        data=await service.collect(
            adapters,
            fetch_timeout_seconds=trend_scheduler.source_timeout_seconds,
        )
    )


@router.get("/runs", response_model=APIResponse[list[TrendRunResponse]])
async def list_trend_runs(
    limit: int = Query(default=20, ge=1, le=100),
    service: TrendService = Depends(get_trend_service),
):
    return APIResponse(data=await service.list_runs(limit=limit))


@router.get(
    "/projects/{project_id}/preferences",
    response_model=APIResponse[TrendPreferencesResponse],
)
async def get_trend_preferences(
    project_id: str,
    service: TrendService = Depends(get_trend_service),
):
    return APIResponse(data=await service.get_preferences(project_id))


@router.patch(
    "/projects/{project_id}/preferences",
    response_model=APIResponse[TrendPreferencesResponse],
)
async def update_trend_preferences(
    project_id: str,
    payload: TrendPreferencesUpdate,
    service: TrendService = Depends(get_trend_service),
):
    return APIResponse(data=await service.update_preferences(project_id, payload))


@router.get(
    "/subscriptions",
    response_model=APIResponse[list[TrendSubscriptionResponse]],
)
async def list_trend_subscriptions(
    project_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return APIResponse(data=await _request_scheduler(db).list_subscriptions(project_id))


@router.post(
    "/subscriptions",
    response_model=APIResponse[TrendSubscriptionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_trend_subscription(
    payload: TrendSubscriptionCreate, db: AsyncSession = Depends(get_db)
):
    return APIResponse(data=await _request_scheduler(db).create_subscription(payload))


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=APIResponse[TrendSubscriptionResponse],
)
async def update_trend_subscription(
    subscription_id: str,
    payload: TrendSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
):
    return APIResponse(
        data=await _request_scheduler(db).update_subscription(subscription_id, payload)
    )


@router.post(
    "/subscriptions/{subscription_id}/run",
    response_model=APIResponse[TrendSubscriptionResponse],
)
async def run_trend_subscription(subscription_id: str, db: AsyncSession = Depends(get_db)):
    return APIResponse(
        data=await _request_scheduler(db).run_subscription(subscription_id, trigger="manual")
    )


@router.post(
    "/proposals",
    response_model=APIResponse[TrendProposalResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_trend_proposal(
    payload: TrendProposalCreate,
    service: TrendService = Depends(get_trend_service),
):
    return APIResponse(data=await service.create_proposal(payload))


@router.patch(
    "/proposals/{proposal_id}",
    response_model=APIResponse[TrendProposalResponse],
)
async def update_trend_proposal(
    proposal_id: str,
    payload: TrendProposalUpdate,
    service: TrendService = Depends(get_trend_service),
):
    return APIResponse(data=await service.update_proposal(proposal_id, payload))


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=APIResponse[TrendProposalResponse],
)
async def reject_trend_proposal(
    proposal_id: str,
    payload: TrendProposalRejectRequest,
    service: TrendService = Depends(get_trend_service),
):
    return APIResponse(data=await service.reject_proposal(proposal_id, payload.expected_revision))


def _proposal_action_response(
    proposal, task, job=None, *, queue_status="not_requested", queue_error=None
):
    task_response_data = task_response(task, scenes_count=0) if task is not None else None
    return TrendProposalActionResponse(
        proposal=proposal,
        task=task_response_data,
        job=job.to_dict() if hasattr(job, "to_dict") else job,
        queue_status=queue_status,
        queue_error=queue_error,
    )


@router.post(
    "/proposals/{proposal_id}/approve-and-create-task",
    response_model=APIResponse[TrendProposalActionResponse],
)
async def approve_trend_proposal(
    proposal_id: str,
    payload: TrendProposalApproveRequest,
    service: TrendService = Depends(get_trend_service),
):
    proposal, task = await service.approve_proposal(proposal_id, payload)
    return APIResponse(data=_proposal_action_response(proposal, task))
