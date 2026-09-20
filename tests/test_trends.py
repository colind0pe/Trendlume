from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.project import ProjectModel
from src.models.trend import (
    TrendObservationModel,
    TrendProjectMatchModel,
    TrendSourceRunModel,
)
from src.services.trend_service import TrendService, normalize_trend_title
from src.services.trend_sources import TrendSourceItem, TrendSourceResult


def _source(
    *,
    source_key: str,
    platform: str,
    status: str = "fresh",
    items: list[dict] | None = None,
    error_message: str | None = None,
    fetched_at: datetime | None = None,
) -> TrendSourceResult:
    return TrendSourceResult(
        source_key=source_key,
        adapter_name="test-fixture",
        platform=platform,
        status=status,
        fetched_at=fetched_at or datetime.now(UTC),
        error_message=error_message,
        items=tuple(TrendSourceItem(**item) for item in (items or [])),
    )


@pytest.mark.asyncio
async def test_trend_run_normalizes_history_and_matches_project(
    client, test_session: AsyncSession
):
    project = ProjectModel(
        id="trend-project",
        name="科技项目",
        mode="knowledge",
        default_production_settings={
            "custom_setting": {"keep": True},
            "trends": {
                "include_keywords": ["AI", "科技"],
                "exclude_keywords": ["抽奖"],
            },
        },
    )
    test_session.add(project)
    await test_session.commit()

    run = await TrendService(test_session).persist_results(
        [
            _source(
                source_key="fixture-weibo",
                platform="weibo",
                items=[
                    {
                        "title": "AI 科技新品!",
                        "rank": 4,
                        "raw_metric": 1200,
                        "metric_unit": "万",
                    },
                    {
                        "title": "AI科技新品",
                        "rank": 1,
                        "raw_metric": "1.5万",
                        "metric_unit": "次",
                    },
                    {
                        "title": "抽奖 福利",
                        "rank": 2,
                        "raw_metric": 900,
                        "metric_unit": "万",
                    },
                ],
            ),
            _source(
                source_key="unavailable-douyin",
                platform="douyin",
                status="unavailable",
                error_message="source timeout",
            ),
        ]
    )
    assert run.status == "partial"
    assert run.success_count == 1
    assert run.error_count == 1
    assert run.error_summary and "source timeout" in run.error_summary

    feed = await client.get(
        "/api/v1/trends",
        params={"project_id": project.id, "freshness": "all"},
    )
    assert feed.status_code == 200
    payload = feed.json()["data"]
    assert payload["status"] == "stale"
    assert len(payload["items"]) == 2
    normalized = normalize_trend_title("AI 科技新品!")
    item = next(
        entry
        for entry in payload["items"]
        if entry["title"] in {"AI 科技新品!", "AI科技新品"}
    )
    assert item["rank"] == 1
    assert item["raw_metric"] == "1.5万"
    assert item["project_relevance"] == "high"
    assert item["source_status"] == "fresh"
    assert item["risk_note"]
    assert normalize_trend_title(item["title"]) == normalized

    observations = list(
        (await test_session.scalars(select(TrendObservationModel))).all()
    )
    source_runs = list((await test_session.scalars(select(TrendSourceRunModel))).all())
    matches = list((await test_session.scalars(select(TrendProjectMatchModel))).all())
    assert len(observations) == 2
    assert len(source_runs) == 2
    assert len(matches) == 2

    await TrendService(test_session).persist_results(
        [
            _source(
                source_key="fixture-weibo",
                platform="weibo",
                fetched_at=datetime.now(UTC) + timedelta(minutes=1),
                items=[
                    {
                        "title": "AI科技新品",
                        "rank": 2,
                        "raw_metric": 1800,
                        "metric_unit": "次",
                    },
                ],
            )
        ]
    )
    assert (
        len(list((await test_session.scalars(select(TrendObservationModel))).all()))
        == 3
    )

    latest = await client.get(
        "/api/v1/trends",
        params={"project_id": project.id, "freshness": "all"},
    )
    latest_item = next(
        entry
        for entry in latest.json()["data"]["items"]
        if entry["title"] in {"AI 科技新品!", "AI科技新品"}
    )
    assert latest_item["rank"] == 2
    assert latest_item["raw_metric"] == "1800"

    preferences = await client.patch(
        f"/api/v1/trends/projects/{project.id}/preferences",
        json={"include_keywords": ["新品"]},
    )
    assert preferences.status_code == 200
    refreshed = await client.get(
        "/api/v1/trends",
        params={"project_id": project.id, "freshness": "all"},
    )
    refreshed_item = next(
        entry
        for entry in refreshed.json()["data"]["items"]
        if entry["title"] in {"AI 科技新品!", "AI科技新品"}
    )
    assert refreshed_item["project_relevance"] == "medium"


@pytest.mark.asyncio
async def test_trend_preferences_patch_preserves_unrelated_project_settings(
    client, test_session: AsyncSession
):
    project = ProjectModel(
        id="trend-preferences-project",
        name="Preferences",
        mode="knowledge",
        default_production_settings={
            "custom_setting": {"keep": True},
            "trends": {"include_keywords": ["old"], "exclude_keywords": ["blocked"]},
        },
    )
    test_session.add(project)
    await test_session.commit()

    response = await client.patch(
        f"/api/v1/trends/projects/{project.id}/preferences",
        json={"include_keywords": ["new"]},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "project_id": project.id,
        "include_keywords": ["new"],
        "exclude_keywords": ["blocked"],
        "platforms": [],
    }

    await test_session.refresh(project)
    assert project.default_production_settings["custom_setting"] == {"keep": True}
    assert project.default_production_settings["trends"]["include_keywords"] == ["new"]
    assert project.default_production_settings["trends"]["exclude_keywords"] == ["blocked"]


@pytest.mark.asyncio
async def test_project_subscription_api_is_idempotent_and_pauseable(
    client, test_session: AsyncSession
):
    project = ProjectModel(
        id="subscription-api-project", name="Subscription API", mode="knowledge"
    )
    test_session.add(project)
    await test_session.commit()

    created = await client.post(
        "/api/v1/trends/subscriptions",
        json={
            "project_id": project.id,
            "frequency": "6h",
            "timezone": "Asia/Shanghai",
            "source_keys": ["fixture-weibo"],
        },
    )
    assert created.status_code == 201
    subscription = created.json()["data"]
    repeated = await client.post(
        "/api/v1/trends/subscriptions",
        json={"project_id": project.id, "frequency": "15m"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["data"]["id"] == subscription["id"]
    assert repeated.json()["data"]["frequency"] == "6h"

    listed = await client.get(
        "/api/v1/trends/subscriptions", params={"project_id": project.id}
    )
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    paused = await client.patch(
        f"/api/v1/trends/subscriptions/{subscription['id']}", json={"enabled": False}
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "paused"
    resumed = await client.patch(
        f"/api/v1/trends/subscriptions/{subscription['id']}", json={"enabled": True}
    )
    assert resumed.status_code == 200
    assert resumed.json()["data"]["enabled"] is True
