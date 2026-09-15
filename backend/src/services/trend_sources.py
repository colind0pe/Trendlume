from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from src.core.config import settings


@dataclass(frozen=True)
class TrendSourceItem:
    title: str
    rank: int
    raw_metric: str | int | float | None = None
    metric_unit: str | None = None
    source_url: str | None = None
    source_updated_at: datetime | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class TrendSourceResult:
    source_key: str
    adapter_name: str
    platform: str
    status: str
    items: tuple[TrendSourceItem, ...] = ()
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_updated_at: datetime | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrendSourceSpec:
    """Configuration for one public hot-list platform."""

    source_key: str
    platform: str
    label: str
    primary_path: str | None
    fallback_path: str | None = None


# These endpoints are the public JSON feeds documented by the reference
# project's trending-topics skill.  Platform home pages are intentionally not
# scraped: they are login/anti-bot surfaces and are not a stable data source.
PUBLIC_HOTLIST_SOURCE_SPECS: tuple[TrendSourceSpec, ...] = (
    TrendSourceSpec("weibo", "weibo", "微博", "/v2/weibo", "/api/weibohot"),
    TrendSourceSpec("douyin", "douyin", "抖音", "/v2/douyin", "/api/douyinhot"),
    TrendSourceSpec("zhihu", "zhihu", "知乎", "/v2/zhihu"),
    TrendSourceSpec("toutiao", "toutiao", "头条", "/v2/toutiao"),
    TrendSourceSpec("xiaohongshu", "xiaohongshu", "小红书", "/v2/rednote"),
    TrendSourceSpec("bilibili", "bilibili", "B 站", None, "/api/bilibilihot"),
    TrendSourceSpec("baidu", "baidu", "百度", "/v2/baidu/hot", "/api/baiduhot"),
)


def _join_url(base_url: str, path: str | None) -> str | None:
    if not path:
        return None
    base = str(base_url or "").strip().rstrip("/")
    return f"{base}/{path.lstrip('/')}" if base else None


def _safe_source_url(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate[:1000]


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        if timestamp <= 0:
            return None
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return _parse_datetime(int(text))
    normalized = text.replace("/", "-")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, pattern)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _mapping_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _payload_items(payload: Any) -> list[Any]:
    """Extract the list from the slightly different public API envelopes."""

    current = payload
    for _ in range(6):
        if isinstance(current, list):
            return current
        if not isinstance(current, dict):
            break
        code = current.get("code")
        if code not in (None, 0, "0", 200, "200", "success"):
            message = str(current.get("message") or current.get("msg") or "接口返回失败")
            raise ValueError(f"source code {code}: {message[:160]}")
        next_value = None
        for key in ("data", "items", "list", "result"):
            if key in current:
                next_value = current[key]
                break
        if next_value is None:
            break
        current = next_value
    raise ValueError("接口返回中没有可解析的热榜列表")


def parse_hotlist_payload(
    payload: Any, *, max_items: int = 50
) -> tuple[TrendSourceItem, ...]:
    """Normalize 60s/xxapi-style payloads without comparing platform metrics."""

    items: list[TrendSourceItem] = []
    for index, raw_item in enumerate(_payload_items(payload), start=1):
        if isinstance(raw_item, str):
            raw_item = {"title": raw_item}
        if not isinstance(raw_item, dict):
            continue
        title_value = _mapping_value(raw_item, ("title", "name", "word", "keyword"))
        title = str(title_value or "").strip()
        if not title:
            continue

        rank_value = _mapping_value(raw_item, ("rank", "index", "position", "sort"))
        try:
            rank = int(rank_value)
        except (TypeError, ValueError):
            rank = index
        if rank < 1:
            rank = index

        metric_value = _mapping_value(
            raw_item,
            (
                "hot_value",
                "hot",
                "score",
                "heat",
                "heat_value",
                "hot_num",
                "hotNumber",
                "value",
                "score_desc",
            ),
        )
        if isinstance(metric_value, (dict, list, tuple, set)):
            metric_value = None
        metric_unit = _mapping_value(raw_item, ("metric_unit", "unit")) or "热度"
        source_updated_at = _parse_datetime(
            _mapping_value(raw_item, ("updated_at", "update_time", "active_time_at", "active_time"))
        )
        published_at = _parse_datetime(
            _mapping_value(
                raw_item,
                (
                    "published_at",
                    "publish_time",
                    "pubdate",
                    "event_time_at",
                    "event_time",
                    "created_at",
                ),
            )
        )
        items.append(
            TrendSourceItem(
                title=title[:500],
                rank=rank,
                raw_metric=metric_value,
                metric_unit=str(metric_unit)[:50],
                source_url=_safe_source_url(
                    _mapping_value(raw_item, ("url", "link", "href"))
                ),
                source_updated_at=source_updated_at,
                published_at=published_at,
            )
        )
        if len(items) >= max(1, max_items):
            break
    return tuple(items)


def _payload_updated_at(payload: Any) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    return _parse_datetime(
        _mapping_value(payload, ("updated_at", "update_time", "timestamp", "updated"))
    )


def _describe_fetch_error(error: Exception) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "请求超时"
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, httpx.RequestError):
        return "网络请求失败"
    message = str(error).strip()
    return message[:180] if message else type(error).__name__


class PublicHotlistAdapter:
    """Fetch one platform's public hot list with a bounded primary/fallback chain."""

    adapter_name = "public-hotlist-failover"

    def __init__(
        self,
        spec: TrendSourceSpec,
        *,
        primary_base_url: str | None = None,
        fallback_base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_items: int | None = None,
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.spec = spec
        self.source_key = spec.source_key
        self.platform = spec.platform
        self.label = spec.label
        self.primary_url = _join_url(
            primary_base_url or settings.trend_source_primary_url,
            spec.primary_path,
        )
        self.fallback_url = _join_url(
            fallback_base_url or settings.trend_source_fallback_url,
            spec.fallback_path,
        )
        self.timeout_seconds = max(
            1.0,
            float(timeout_seconds or settings.trend_source_request_timeout_seconds),
        )
        self.max_items = max(1, int(max_items or settings.trend_source_max_items))
        self.client_factory = client_factory or httpx.AsyncClient
        self.transport = transport

    @property
    def fallback_available(self) -> bool:
        return self.fallback_url is not None

    async def fetch(self) -> TrendSourceResult:
        fetched_at = datetime.now(UTC)
        endpoints = [
            ("60s", self.primary_url),
            ("xxapi", self.fallback_url),
        ]
        attempts: list[str] = []
        client_options: dict[str, Any] = {
            "timeout": self.timeout_seconds,
            "follow_redirects": True,
            # The reference workflow uses the trusted environment proxy.  Do
            # the same here so local and Docker deployments honor HTTPS_PROXY.
            "trust_env": True,
            "headers": {
                "Accept": "application/json",
                "User-Agent": "Trendlume/0.1 (+https://github.com/colind0pe/Trendlume)",
            },
        }
        if self.transport is not None:
            client_options["transport"] = self.transport

        try:
            async with self.client_factory(**client_options) as client:
                for provider, endpoint in endpoints:
                    if not endpoint:
                        continue
                    try:
                        response = await client.get(endpoint)
                        response.raise_for_status()
                        payload = response.json()
                        items = parse_hotlist_payload(payload, max_items=self.max_items)
                        if not items:
                            raise ValueError("接口返回了空热榜")
                        source_updated_at = _payload_updated_at(payload) or next(
                            (item.source_updated_at for item in items if item.source_updated_at),
                            None,
                        )
                        summary = f"{self.label} · {provider} 公益热榜接口"
                        if provider == "xxapi":
                            summary += "（主源失败后切换备用源）"
                        return TrendSourceResult(
                            source_key=self.source_key,
                            adapter_name=self.adapter_name,
                            platform=self.platform,
                            status="fresh",
                            items=items,
                            fetched_at=fetched_at,
                            source_updated_at=source_updated_at,
                            metadata={
                                "summary": summary,
                                "provider": provider,
                                "endpoint": endpoint,
                                "fallback_used": provider == "xxapi",
                                "attempts": attempts + [f"{provider}:ok"],
                            },
                        )
                    except Exception as error:
                        attempts.append(f"{provider}: {_describe_fetch_error(error)}")
        except Exception as error:
            attempts.append(f"client: {_describe_fetch_error(error)}")

        return TrendSourceResult(
            source_key=self.source_key,
            adapter_name=self.adapter_name,
            platform=self.platform,
            status="unavailable",
            fetched_at=fetched_at,
            error_message=("；".join(attempts) or "没有配置可用的公开热榜接口。")[:2000],
            metadata={
                "summary": f"{self.label} 公开热榜来源不可用",
                "attempts": attempts,
            },
        )


def default_trend_source_adapters() -> tuple[PublicHotlistAdapter, ...]:
    """Build the production registry entries from environment configuration."""

    return tuple(
        PublicHotlistAdapter(spec)
        for spec in PUBLIC_HOTLIST_SOURCE_SPECS
    )


class TrendSourceAdapter(Protocol):
    """Replaceable boundary for a platform source; adapters return normalized data."""

    async def fetch(self) -> TrendSourceResult:
        ...
