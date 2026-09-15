import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.project import ProjectModel
from src.models.trend import (
    TopicProposalModel,
    TrendItemModel,
    TrendRunModel,
    TrendSubscriptionModel,
)
from src.schemas.trend import TrendProposalCreate, TrendSubscriptionCreate
from src.services.trend_scheduler import (
    TrendScheduler,
    TrendSourceRegistry,
    next_run_after,
)
from src.services.trend_service import TrendService
from src.services.trend_sources import TrendSourceItem, TrendSourceResult


class FixtureAdapter:
    source_key = "fixture-weibo"
    platform = "weibo"

    def __init__(self, result: TrendSourceResult | None = None):
        self.calls = 0
        self.result = result or TrendSourceResult(
            source_key=self.source_key,
            adapter_name="fixture",
            platform=self.platform,
            status="fresh",
            items=(TrendSourceItem(title="AI scheduler", rank=1, raw_metric="10"),),
        )

    async def fetch(self):
        self.calls += 1
        return self.result


class SlowAdapter(FixtureAdapter):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch(self):
        self.started.set()
        await self.release.wait()
        return await super().fetch()


async def _scheduler(test_session: AsyncSession, adapter=None) -> tuple[TrendScheduler, async_sessionmaker]:
    factory = async_sessionmaker(test_session.bind, expire_on_commit=False, class_=AsyncSession)
    registry = TrendSourceRegistry()
    if adapter is not None:
        registry.register(adapter.source_key, adapter)
    return TrendScheduler(factory, registry=registry, lease_seconds=10, poll_interval_seconds=60), factory


async def _project(session: AsyncSession, project_id: str = "scheduler-project"):
    project = ProjectModel(id=project_id, name="Scheduler project")
    session.add(project)
    await session.commit()
    return project


@pytest.mark.asyncio
async def test_subscription_timezone_and_success_run_are_durable(test_session: AsyncSession):
    await _project(test_session)
    adapter = FixtureAdapter()
    scheduler, _ = await _scheduler(test_session, adapter)
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    created = await scheduler.create_subscription(
        TrendSubscriptionCreate(
            project_id="scheduler-project",
            frequency="1h",
            timezone="Asia/Shanghai",
            source_keys=[adapter.source_key],
        ),
        now=start,
    )
    assert created.next_run_at == start
    assert next_run_after(start, "1h", "Asia/Shanghai") == datetime(2026, 1, 1, 1, 0, tzinfo=UTC)
    assert next_run_after(datetime(2026, 1, 1), "1h", "UTC") == datetime(
        2026, 1, 1, 1, 0, tzinfo=UTC
    )

    result = await scheduler.run_subscription(
        created.id, trigger="scheduled", now=start, trigger_key="scheduled:slot-1"
    )
    assert result.status == "active"
    assert result.last_success_at == start
    assert result.recent_runs[0].status == "completed"
    assert adapter.calls == 1
    assert await test_session.scalar(select(func.count()).select_from(TrendRunModel)) == 1

    # The same scheduled slot is idempotent after completion and does not
    # fetch the source again.
    duplicate = await scheduler.run_subscription(
        created.id, trigger="scheduled", now=start, trigger_key="scheduled:slot-1"
    )
    assert duplicate.last_run_id == result.last_run_id
    assert adapter.calls == 1
    assert await test_session.scalar(select(func.count()).select_from(TrendRunModel)) == 1


@pytest.mark.asyncio
async def test_concurrent_trigger_is_fenced_to_one_collection(test_session: AsyncSession):
    await _project(test_session, "concurrent-project")
    adapter = SlowAdapter()
    scheduler, _ = await _scheduler(test_session, adapter)
    created = await scheduler.create_subscription(
        TrendSubscriptionCreate(
            project_id="concurrent-project", source_keys=[adapter.source_key]
        ),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    first = asyncio.create_task(
        scheduler.run_subscription(
            created.id, trigger="scheduled", now=datetime(2026, 1, 1, tzinfo=UTC), trigger_key="slot"
        )
    )
    await adapter.started.wait()
    second = await scheduler.run_subscription(
        created.id, trigger="scheduled", now=datetime(2026, 1, 1, tzinfo=UTC), trigger_key="slot"
    )
    assert second.status == "running"
    adapter.release.set()
    result = await first
    assert result.status == "active"
    assert adapter.calls == 1
    assert await test_session.scalar(select(func.count()).select_from(TrendRunModel)) == 1


@pytest.mark.asyncio
async def test_new_collection_refreshes_open_proposal_without_duplicate(test_session: AsyncSession):
    await _project(test_session, "proposal-refresh-project")
    adapter = FixtureAdapter()
    scheduler, factory = await _scheduler(test_session, adapter)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    created = await scheduler.create_subscription(
        TrendSubscriptionCreate(
            project_id="proposal-refresh-project", source_keys=[adapter.source_key]
        ),
        now=start,
    )
    first = await scheduler.run_subscription(
        created.id, trigger="scheduled", now=start, trigger_key="slot-1"
    )
    trend_item = await test_session.scalar(select(TrendItemModel))
    assert trend_item is not None
    proposal = await TrendService(test_session).create_proposal(
        TrendProposalCreate(
            project_id="proposal-refresh-project", trend_item_id=trend_item.id
        )
    )
    adapter.result = TrendSourceResult(
        source_key=adapter.source_key,
        adapter_name="fixture",
        platform=adapter.platform,
        status="fresh",
        items=(TrendSourceItem(title="AI scheduler", rank=2, raw_metric="20"),),
    )
    async with factory() as session:
        subscription = await session.get(TrendSubscriptionModel, created.id)
        subscription.next_run_at = (start + timedelta(hours=1)).replace(tzinfo=None)
        await session.commit()
    second = await scheduler.run_subscription(
        created.id,
        trigger="scheduled",
        now=start + timedelta(hours=1),
        trigger_key="slot-2",
    )
    refreshed = await test_session.get(TopicProposalModel, proposal.id)
    assert refreshed is not None
    assert refreshed.trend_run_id == second.last_run_id
    assert refreshed.trend_snapshot["rank"] == 2
    assert await test_session.scalar(select(func.count()).select_from(TopicProposalModel)) == 1
    assert first.last_run_id != second.last_run_id
