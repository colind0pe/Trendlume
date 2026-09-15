"""Durable project trend subscriptions and their lease-fenced scheduler."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.exceptions import ConflictException, NotFoundException, ValidationException
from src.models.project import ProjectModel
from src.models.trend import (
    TrendRunModel,
    TrendSourceRunModel,
    TrendSubscriptionModel,
)
from src.schemas.trend import (
    TrendSubscriptionCreate,
    TrendSubscriptionResponse,
    TrendSubscriptionUpdate,
)
from src.services.trend_common import as_utc, clean_terms
from src.services.trend_service import TrendService, build_trend_run_response
from src.services.trend_sources import TrendSourceAdapter, default_trend_source_adapters

FREQUENCY_MINUTES = {"15m": 15, "1h": 60, "6h": 360, "24h": 1440}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _db_time(value: datetime) -> datetime:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(tzinfo=None)


def validate_timezone(value: str) -> str:
    timezone = str(value or "UTC").strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationException(f"不支持的时区：{timezone}") from exc
    return timezone


def frequency_delta(frequency: str) -> timedelta:
    try:
        return timedelta(minutes=FREQUENCY_MINUTES[frequency])
    except KeyError as exc:
        raise ValidationException("采集频率必须是 15m、1h、6h 或 24h。") from exc


def next_run_after(moment: datetime, frequency: str, timezone: str) -> datetime:
    """Advance in project-local time, then persist the UTC instant."""

    validate_timezone(timezone)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    local = moment.astimezone(ZoneInfo(timezone))
    return (local + frequency_delta(frequency)).astimezone(UTC)


class TrendSourceRegistry:
    """Explicit source adapter registry; no unconfigured source is fabricated."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], TrendSourceAdapter] | TrendSourceAdapter] = {}

    def register(
        self,
        source_key: str,
        adapter: Callable[[], TrendSourceAdapter] | TrendSourceAdapter,
    ) -> None:
        key = str(source_key).strip()
        if not key:
            raise ValueError("source_key cannot be empty")
        self._factories[key] = adapter

    def resolve(
        self, source_keys: Sequence[str], platforms: Sequence[str]
    ) -> list[TrendSourceAdapter]:
        requested = {str(item).strip().casefold() for item in source_keys if str(item).strip()}
        if "all" in requested:
            requested.remove("all")
        platform_keys = {str(item).strip().casefold() for item in platforms if str(item).strip()}
        platform_keys.discard("all")
        adapters: list[TrendSourceAdapter] = []
        for key, factory in self._factories.items():
            if requested and key.casefold() not in requested:
                continue
            adapter = factory() if callable(factory) else factory
            if (
                platform_keys
                and str(getattr(adapter, "platform", "")).casefold() not in platform_keys
            ):
                continue
            adapters.append(adapter)
        return adapters

    def registered_keys(self) -> list[str]:
        return list(self._factories)

    def registered_platforms(self) -> set[str]:
        return {
            str(getattr(adapter, "platform", "")).strip().casefold()
            for adapter in self.resolve([], [])
            if str(getattr(adapter, "platform", "")).strip()
        }


class TrendScheduler:
    """Lease-fenced scheduler for project subscriptions.

    Collection runs are persisted in trend tables and never enter
    ``workflow_jobs`` because they have no Task to execute.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker | None = None,
        *,
        registry: TrendSourceRegistry | None = None,
        lease_seconds: float = 120.0,
        source_timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self.session_factory = session_factory or async_session_factory
        self.registry = registry or TrendSourceRegistry()
        self.lease_seconds = max(5.0, float(lease_seconds))
        self.source_timeout_seconds = max(0.1, float(source_timeout_seconds))
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self._running = False
        self._poller: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.recover_expired_leases()
        self._poller = asyncio.create_task(self._poll_loop(), name="TrendScheduler-Poller")
        logger.info("Trend subscription scheduler started.")

    async def stop(self) -> None:
        self._running = False
        if self._poller and not self._poller.done():
            self._poller.cancel()
            await asyncio.gather(self._poller, return_exceptions=True)
        self._poller = None
        logger.info("Trend subscription scheduler stopped.")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Trend scheduler poll failed: {}", exc)
            await asyncio.sleep(self.poll_interval_seconds)

    async def tick(self, now: datetime | None = None) -> list[TrendSubscriptionResponse]:
        instant = now or _utc_now()
        db_now = _db_time(instant)
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(TrendSubscriptionModel).where(
                        TrendSubscriptionModel.enabled.is_(True),
                        TrendSubscriptionModel.status != "paused",
                        TrendSubscriptionModel.next_run_at.is_not(None),
                        TrendSubscriptionModel.next_run_at <= db_now,
                    )
                )
            ).all()
            ids = [row.id for row in rows]
        if not ids:
            return []
        # Each subscription has its own lease, so independent projects can run
        # concurrently while duplicate ticks for one project remain fenced.
        results = await asyncio.gather(
            *(self.run_subscription(item, trigger="scheduled", now=instant) for item in ids),
            return_exceptions=True,
        )
        responses: list[TrendSubscriptionResponse] = []
        for result in results:
            if isinstance(result, TrendSubscriptionResponse):
                responses.append(result)
            elif isinstance(result, Exception):
                logger.error("Trend subscription tick failed: {}", result)
        return responses

    async def recover_expired_leases(self, now: datetime | None = None) -> int:
        instant = now or _utc_now()
        db_now = _db_time(instant)
        async with self.session_factory() as session:
            expired_ids = list(
                (
                    await session.scalars(
                        select(TrendSubscriptionModel.id).where(
                            TrendSubscriptionModel.status == "running",
                            TrendSubscriptionModel.lease_expires_at.is_not(None),
                            TrendSubscriptionModel.lease_expires_at < db_now,
                        )
                    )
                ).all()
            )
            if not expired_ids:
                return 0
            result = await session.execute(
                update(TrendSubscriptionModel)
                .where(
                    TrendSubscriptionModel.id.in_(expired_ids),
                    TrendSubscriptionModel.status == "running",
                    TrendSubscriptionModel.lease_expires_at.is_not(None),
                    TrendSubscriptionModel.lease_expires_at < db_now,
                )
                .values(
                    status="stale",
                    enabled=True,
                    retry_count=TrendSubscriptionModel.retry_count + 1,
                    next_run_at=db_now,
                    last_error="采集租约已过期，已安排恢复运行。",
                    lease_token=None,
                    lease_expires_at=None,
                    updated_at=db_now,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount:
                # A process can die after creating a running TrendRun but
                # before persisting its final result.  Mark that attempt stale
                # so the UI and restart recovery do not show it forever.
                await session.execute(
                    update(TrendRunModel)
                    .where(
                        TrendRunModel.subscription_id.in_(expired_ids),
                        TrendRunModel.status == "running",
                    )
                    .values(
                        status="stale",
                        error_summary="采集租约已过期，运行结果未完成。",
                        completed_at=db_now,
                    )
                    .execution_options(synchronize_session=False)
                )
            await session.commit()
            return int(result.rowcount or 0)

    async def create_subscription(
        self, payload: TrendSubscriptionCreate, *, now: datetime | None = None
    ) -> TrendSubscriptionResponse:
        timezone = validate_timezone(payload.timezone)
        frequency_delta(payload.frequency)
        instant = now or _utc_now()
        async with self.session_factory() as session:
            project = await session.get(ProjectModel, payload.project_id)
            if project is None:
                raise NotFoundException("Project", payload.project_id)
            existing = await session.scalar(
                select(TrendSubscriptionModel).where(
                    TrendSubscriptionModel.project_id == payload.project_id
                )
            )
            if existing is None:
                existing = TrendSubscriptionModel(
                    id=f"trend_sub_{uuid4().hex[:12]}",
                    project_id=payload.project_id,
                    enabled=payload.enabled,
                    platforms=clean_terms(payload.platforms, limit=30),
                    source_keys=clean_terms(payload.source_keys, limit=50),
                    frequency=payload.frequency,
                    timezone=timezone,
                    status="active" if payload.enabled else "paused",
                    retry_count=0,
                    next_run_at=_db_time(instant) if payload.enabled else None,
                    created_at=_db_time(instant),
                    updated_at=_db_time(instant),
                )
                session.add(existing)
            try:
                await session.commit()
            except IntegrityError:
                # Two retries may race before either sees the project-level
                # unique row.  Roll back this scheduler transaction and return
                # the winner, preserving POST idempotence.
                await session.rollback()
                existing = await session.scalar(
                    select(TrendSubscriptionModel).where(
                        TrendSubscriptionModel.project_id == payload.project_id
                    )
                )
                if existing is None:
                    raise
            return await self._response(session, existing)

    async def get_subscription(self, subscription_id: str) -> TrendSubscriptionResponse:
        async with self.session_factory() as session:
            subscription = await session.get(TrendSubscriptionModel, subscription_id)
            if subscription is None:
                raise NotFoundException("Trend subscription", subscription_id)
            return await self._response(session, subscription)

    async def list_subscriptions(
        self, project_id: str | None = None
    ) -> list[TrendSubscriptionResponse]:
        async with self.session_factory() as session:
            stmt = select(TrendSubscriptionModel).order_by(TrendSubscriptionModel.created_at.desc())
            if project_id:
                if await session.get(ProjectModel, project_id) is None:
                    raise NotFoundException("Project", project_id)
                stmt = stmt.where(TrendSubscriptionModel.project_id == project_id)
            rows = (await session.scalars(stmt)).all()
            return [await self._response(session, row) for row in rows]

    async def update_subscription(
        self,
        subscription_id: str,
        payload: TrendSubscriptionUpdate,
        *,
        now: datetime | None = None,
    ) -> TrendSubscriptionResponse:
        instant = now or _utc_now()
        async with self.session_factory() as session:
            subscription = await session.get(TrendSubscriptionModel, subscription_id)
            if subscription is None:
                raise NotFoundException("Trend subscription", subscription_id)
            policy_changed = any(
                value is not None
                for value in (
                    payload.platforms,
                    payload.source_keys,
                    payload.frequency,
                    payload.timezone,
                )
            )
            if payload.timezone is not None:
                subscription.timezone = validate_timezone(payload.timezone)
            if payload.frequency is not None:
                frequency_delta(payload.frequency)
                subscription.frequency = payload.frequency
            if payload.platforms is not None:
                subscription.platforms = clean_terms(payload.platforms, limit=30)
            if payload.source_keys is not None:
                subscription.source_keys = clean_terms(payload.source_keys, limit=50)
            if payload.enabled is not None:
                subscription.enabled = payload.enabled
                if payload.enabled:
                    if subscription.status == "paused":
                        subscription.status = "active"
                    subscription.next_run_at = _db_time(instant)
                else:
                    subscription.status = "paused"
                    subscription.next_run_at = None
                    subscription.lease_token = None
                    subscription.lease_expires_at = None
            elif policy_changed and subscription.enabled and subscription.status != "paused":
                # A changed policy takes effect on the next scheduler tick;
                # do not leave an old far-future due time behind.
                subscription.next_run_at = _db_time(instant)
            subscription.updated_at = _db_time(instant)
            await session.commit()
            return await self._response(session, subscription)

    async def run_subscription(
        self,
        subscription_id: str,
        *,
        trigger: str = "manual",
        trigger_key: str | None = None,
        now: datetime | None = None,
    ) -> TrendSubscriptionResponse:
        instant = now or _utc_now()
        db_now = _db_time(instant)
        await self.recover_expired_leases(instant)
        lease_token = uuid4().hex
        run_id: str | None = None
        async with self.session_factory() as session:
            subscription = await session.get(TrendSubscriptionModel, subscription_id)
            if subscription is None:
                raise NotFoundException("Trend subscription", subscription_id)
            if trigger == "manual" and subscription.status == "paused":
                raise ConflictException("趋势订阅已暂停，请恢复后再手动运行。")
            if trigger == "scheduled" and (
                not subscription.enabled
                or subscription.status == "paused"
                or subscription.next_run_at is None
                or subscription.next_run_at > db_now
            ):
                return await self._response(session, subscription)
            key = trigger_key or (
                f"scheduled:{subscription.next_run_at.isoformat()}"
                if trigger == "scheduled"
                else f"manual:{uuid4().hex}"
            )
            existing_run = await session.scalar(
                select(TrendRunModel).where(
                    TrendRunModel.subscription_id == subscription.id,
                    TrendRunModel.trigger_key == key,
                    TrendRunModel.status != "running",
                )
            )
            if existing_run is not None:
                return await self._response(session, subscription)
            claimed = await session.execute(
                update(TrendSubscriptionModel)
                .where(
                    TrendSubscriptionModel.id == subscription.id,
                    TrendSubscriptionModel.enabled.is_(True),
                    TrendSubscriptionModel.status != "paused",
                    or_(
                        TrendSubscriptionModel.lease_expires_at.is_(None),
                        TrendSubscriptionModel.lease_expires_at < db_now,
                    ),
                    *(
                        [TrendSubscriptionModel.next_run_at <= db_now]
                        if trigger == "scheduled"
                        else []
                    ),
                )
                .values(
                    status="running",
                    lease_token=lease_token,
                    lease_expires_at=db_now + timedelta(seconds=self.lease_seconds),
                    last_started_at=db_now,
                    last_error=None,
                    updated_at=db_now,
                )
                .execution_options(synchronize_session=False)
            )
            if claimed.rowcount != 1:
                current = await session.get(TrendSubscriptionModel, subscription.id)
                if current is None:
                    raise NotFoundException("Trend subscription", subscription_id)
                return await self._response(session, current)
            await session.commit()

        heartbeat = asyncio.create_task(
            self._renew_lease(subscription_id, lease_token),
            name=f"TrendSubscriptionLease-{subscription_id}",
        )
        try:
            async with self.session_factory() as session:
                current = await session.get(TrendSubscriptionModel, subscription_id)
                if current is None:
                    raise NotFoundException("Trend subscription", subscription_id)
                adapters = self.registry.resolve(current.source_keys or [], current.platforms or [])
                # Commit a running TrendRun before any network-bound source
                # request.  If the process dies while an adapter is waiting,
                # restart recovery can mark this exact run stale instead of
                # leaving an invisible attempt behind.
                run_id = f"trend_run_{uuid4().hex[:12]}"
                running_run = TrendRunModel(
                    id=run_id,
                    status="running",
                    requested_platforms=sorted(
                        {str(getattr(adapter, "platform", "unknown")) for adapter in adapters}
                    ),
                    source_count=len(adapters),
                    started_at=db_now,
                    created_at=db_now,
                    subscription_id=subscription_id,
                    trigger_key=key,
                )
                session.add(running_run)
                await session.commit()
                # An empty registry is an explicit unavailable boundary.  The
                # failed run is still persisted, so the UI can explain why no
                # fresh trend data exists instead of showing a fake success.
                run = await TrendService(session).collect(
                    adapters,
                    subscription_id=subscription_id,
                    trigger_key=key,
                    run_id=run_id,
                    fetch_timeout_seconds=self.source_timeout_seconds,
                )
                # Policy updates may arrive while an adapter is in flight.
                # Refresh before calculating the next slot so a stale
                # frequency/timezone snapshot cannot overwrite the new policy.
                await session.refresh(current)
                outcome_status = (
                    "active"
                    if run.status == "completed"
                    else (
                        "stale"
                        if run.status == "partial"
                        else "unavailable"
                        if not adapters
                        else "failed"
                    )
                )
                error = "没有注册可用的趋势 source adapter。" if not adapters else run.error_summary
                next_due = next_run_after(
                    instant,
                    current.frequency,
                    current.timezone,
                )
                retry_count = 0 if run.status == "completed" else current.retry_count + 1
                if run.status != "completed":
                    backoff = min(
                        frequency_delta(current.frequency).total_seconds()
                        * (2 ** min(retry_count, 4)),
                        6 * 3600,
                    )
                    next_due = instant + timedelta(seconds=backoff)
                result = await session.execute(
                    update(TrendSubscriptionModel)
                    .where(
                        TrendSubscriptionModel.id == subscription_id,
                        TrendSubscriptionModel.lease_token == lease_token,
                        TrendSubscriptionModel.status == "running",
                    )
                    .values(
                        status=outcome_status,
                        retry_count=retry_count,
                        last_run_id=run.id,
                        last_success_at=db_now
                        if run.status == "completed"
                        else current.last_success_at,
                        next_run_at=_db_time(next_due),
                        last_error=error,
                        lease_token=None,
                        lease_expires_at=None,
                        updated_at=_db_time(instant),
                    )
                    .execution_options(synchronize_session=False)
                )
                await session.commit()
                if result.rowcount != 1:
                    logger.warning("Trend subscription lease lost after run {}", run.id)
        except Exception as exc:
            safe_error = str(exc)[:2000] or type(exc).__name__
            async with self.session_factory() as session:
                if run_id:
                    await session.execute(
                        update(TrendRunModel)
                        .where(
                            TrendRunModel.id == run_id,
                            TrendRunModel.status == "running",
                        )
                        .values(
                            status="failed",
                            error_summary=safe_error,
                            completed_at=_db_time(instant),
                        )
                        .execution_options(synchronize_session=False)
                    )
                await session.execute(
                    update(TrendSubscriptionModel)
                    .where(
                        TrendSubscriptionModel.id == subscription_id,
                        TrendSubscriptionModel.lease_token == lease_token,
                    )
                    .values(
                        status="failed",
                        retry_count=TrendSubscriptionModel.retry_count + 1,
                        next_run_at=_db_time(instant + timedelta(minutes=5)),
                        last_error=safe_error,
                        lease_token=None,
                        lease_expires_at=None,
                        updated_at=_db_time(instant),
                    )
                    .execution_options(synchronize_session=False)
                )
                await session.commit()
            logger.error("Trend subscription {} failed: {}", subscription_id, safe_error)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

        return await self.get_subscription(subscription_id)

    async def _renew_lease(self, subscription_id: str, lease_token: str) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            now = _utc_now()
            try:
                async with self.session_factory() as session:
                    result = await session.execute(
                        update(TrendSubscriptionModel)
                        .where(
                            TrendSubscriptionModel.id == subscription_id,
                            TrendSubscriptionModel.status == "running",
                            TrendSubscriptionModel.lease_token == lease_token,
                        )
                        .values(
                            lease_expires_at=_db_time(now + timedelta(seconds=self.lease_seconds)),
                            updated_at=_db_time(now),
                        )
                        .execution_options(synchronize_session=False)
                    )
                    await session.commit()
                    if result.rowcount != 1:
                        # Another worker fenced this lease or the subscription
                        # was paused; stop renewing a token we no longer own.
                        return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A transient SQLite lock must not kill the heartbeat task.
                # The next pulse retries; final writes remain token-fenced.
                logger.warning(
                    "Trend subscription lease renewal failed for {}: {}",
                    subscription_id,
                    exc,
                )

    async def _response(
        self, session: AsyncSession, subscription: TrendSubscriptionModel
    ) -> TrendSubscriptionResponse:
        runs = []
        if subscription.id:
            run_rows = list(
                (
                    await session.scalars(
                        select(TrendRunModel)
                        .where(TrendRunModel.subscription_id == subscription.id)
                        .order_by(TrendRunModel.started_at.desc())
                        .limit(5)
                    )
                ).all()
            )
            # ``last_run_id`` is the lease-fenced completion pointer.  Keep
            # that exact run first even when restored rows have clock-skewed
            # timestamps (or a test supplies a synthetic scheduler clock).
            if subscription.last_run_id:
                last_index = next(
                    (
                        index
                        for index, row in enumerate(run_rows)
                        if row.id == subscription.last_run_id
                    ),
                    None,
                )
                if last_index is None:
                    last_run = await session.get(TrendRunModel, subscription.last_run_id)
                    if last_run is not None:
                        run_rows.insert(0, last_run)
                elif last_index:
                    run_rows.insert(0, run_rows.pop(last_index))
            run_rows = run_rows[:5]
            source_rows = (
                (
                    await session.scalars(
                        select(TrendSourceRunModel)
                        .where(TrendSourceRunModel.run_id.in_([row.id for row in run_rows]))
                        .order_by(TrendSourceRunModel.created_at.asc())
                    )
                ).all()
                if run_rows
                else []
            )
            source_map: dict[str, list[TrendSourceRunModel]] = {}
            for row in source_rows:
                source_map.setdefault(row.run_id, []).append(row)
            runs = [build_trend_run_response(row, source_map.get(row.id, [])) for row in run_rows]
        latest_sources = runs[0].sources if runs else []
        source_health = [
            {
                "source_key": source.source_key,
                "platform": source.platform,
                "status": source.status,
                "item_count": source.item_count,
                "fetched_at": source.fetched_at,
                "error_message": source.error_message,
            }
            for source in latest_sources
        ]
        return TrendSubscriptionResponse(
            id=subscription.id,
            project_id=subscription.project_id,
            enabled=subscription.enabled,
            platforms=list(subscription.platforms or []),
            source_keys=list(subscription.source_keys or []),
            frequency=subscription.frequency,
            timezone=subscription.timezone,
            status=subscription.status,
            retry_count=subscription.retry_count,
            last_run_id=subscription.last_run_id,
            last_started_at=as_utc(subscription.last_started_at),
            last_success_at=as_utc(subscription.last_success_at),
            next_run_at=as_utc(subscription.next_run_at),
            last_error=subscription.last_error,
            recent_runs=runs,
            source_health=source_health,
            created_at=as_utc(subscription.created_at),
            updated_at=as_utc(subscription.updated_at),
        )


trend_source_registry = TrendSourceRegistry()
for _adapter in default_trend_source_adapters():
    trend_source_registry.register(_adapter.source_key, _adapter)
trend_scheduler = TrendScheduler(
    registry=trend_source_registry,
    lease_seconds=120.0,
    source_timeout_seconds=getattr(settings, "trend_scheduler_source_timeout_seconds", 60.0),
    poll_interval_seconds=getattr(settings, "trend_scheduler_poll_interval_seconds", 30.0),
)
