import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime

PLATFORM_LABELS = {
    "weibo": "微博",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "zhihu": "知乎",
    "bilibili": "B 站",
    "toutiao": "头条",
    "baidu": "百度",
}

RELATION_PRIORITY = {"high": 3, "medium": 2, "low": 1, "unknown": 0}


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize SQLite-naive timestamps at API and proposal boundaries."""

    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def clean_terms(values: Sequence[str] | None, *, limit: int = 100) -> list[str]:
    """Normalize and de-duplicate user-configured trend terms."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        term = unicodedata.normalize("NFKC", str(value)).strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(term[:100])
    return result[:limit]


def build_trend_snapshot(
    *,
    title: str,
    platform: str,
    rank: int,
    raw_metric: str | None,
    metric_unit: str | None,
    source_url: str | None,
    fetched_at: datetime | None,
    source_status: str,
    source_key: str,
    adapter_name: str,
    run_id: str,
) -> dict:
    """Serialize the stable source context carried by a TopicProposal."""

    return {
        "title": title,
        "platform": platform,
        "platform_label": PLATFORM_LABELS.get(platform, platform),
        "rank": rank,
        "raw_metric": raw_metric,
        "metric_unit": metric_unit,
        "source_url": source_url,
        "fetched_at": as_utc(fetched_at).isoformat() if fetched_at else None,
        "source_status": source_status,
        "source_key": source_key,
        "adapter_name": adapter_name,
        "run_id": run_id,
    }


def relation_priority(relation: str) -> int:
    return RELATION_PRIORITY.get(relation, 0)


def prefer_match(
    current: tuple[str, str, list[str]] | None,
    candidate: tuple[str, str, list[str]],
) -> tuple[str, str, list[str]]:
    if current is None or relation_priority(candidate[0]) > relation_priority(current[0]):
        return candidate
    return current
