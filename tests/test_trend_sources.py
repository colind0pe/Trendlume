import httpx
import pytest

from src.api.routes import trends as trends_route
from src.services.trend_scheduler import TrendSourceRegistry
from src.services.trend_sources import (
    PUBLIC_HOTLIST_SOURCE_SPECS,
    PublicHotlistAdapter,
    TrendSourceResult,
    parse_hotlist_payload,
)


def test_parse_hotlist_payload_supports_v2_envelopes_and_source_fields():
    items = parse_hotlist_payload(
        {
            "code": 200,
            "data": {
                "data": [
                    {
                        "title": "AI 新品发布",
                        "hot_value": 123456,
                        "link": "https://example.com/topic",
                        "event_time_at": 1_700_000_000,
                    },
                    {"title": "第二条", "score_desc": "9.8w"},
                ],
            },
        },
        max_items=10,
    )

    assert len(items) == 2
    assert items[0].rank == 1
    assert items[0].raw_metric == 123456
    assert items[0].source_url == "https://example.com/topic"
    assert items[0].published_at is not None
    assert items[1].raw_metric == "9.8w"


async def _fallback_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "primary.example":
        return httpx.Response(503, request=request)
    return httpx.Response(
        200,
        json={"code": 200, "data": [{"title": "备用热点", "hot": "42"}]},
        request=request,
    )


@pytest.mark.asyncio
async def test_public_hotlist_adapter_falls_back_to_xxapi():
    spec = PUBLIC_HOTLIST_SOURCE_SPECS[0]
    adapter = PublicHotlistAdapter(
        spec,
        primary_base_url="https://primary.example",
        fallback_base_url="https://fallback.example",
        transport=httpx.MockTransport(_fallback_handler),
        timeout_seconds=1,
    )

    result = await adapter.fetch()

    assert result.status == "fresh"
    assert result.metadata["provider"] == "xxapi"
    assert result.metadata["fallback_used"] is True
    assert result.metadata["attempts"] == ["60s: HTTP 503", "xxapi:ok"]
    assert result.items[0].title == "备用热点"


@pytest.mark.asyncio
async def test_refresh_endpoint_persists_registered_adapter(client, monkeypatch):
    # Keep the endpoint test deterministic while exercising the same route
    # used by the real source registry.
    class Adapter:
        source_key = "fixture-refresh"
        platform = "weibo"
        adapter_name = "fixture-refresh"

        async def fetch(self):
            from src.services.trend_sources import TrendSourceItem

            return TrendSourceResult(
                source_key=self.source_key,
                adapter_name=self.adapter_name,
                platform=self.platform,
                status="fresh",
                items=(TrendSourceItem(title="实时刷新热点", rank=1, raw_metric="99"),),
            )

    registry = TrendSourceRegistry()
    registry.register("fixture-refresh", Adapter())
    monkeypatch.setattr(trends_route.trend_scheduler, "registry", registry)

    catalog = await client.get("/api/v1/trends/sources")
    assert catalog.status_code == 200
    assert catalog.json()["data"][0]["platform"] == "weibo"

    response = await client.post(
        "/api/v1/trends/refresh",
        json={"source_keys": ["fixture-refresh"]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    feed = await client.get("/api/v1/trends", params={"freshness": "all"})
    assert feed.json()["data"]["items"][0]["title"] == "实时刷新热点"
