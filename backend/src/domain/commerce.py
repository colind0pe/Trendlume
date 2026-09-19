from __future__ import annotations

from src.domain.enums import CreativeAngle

CREATIVE_ANGLE_LABELS = {
    CreativeAngle.DIRECT.value: "直接介绍",
    CreativeAngle.PAIN_POINT.value: "痛点切入",
    CreativeAngle.USE_CASE.value: "使用场景",
    CreativeAngle.DEMO.value: "功能演示",
    CreativeAngle.REVIEW.value: "真实测评",
    CreativeAngle.COMPARISON.value: "对比选择",
    CreativeAngle.STORY.value: "故事叙事",
}

DYNAMIC_FACT_TOKENS = frozenset(
    {
        "price",
        "sale_price",
        "original_price",
        "discount",
        "promotion",
        "activity",
        "coupon",
        "价格",
        "折扣",
        "优惠",
        "活动",
        "促销",
        "券",
    }
)


def is_dynamic_fact_field(field: str) -> bool:
    normalized = str(field or "").strip().lower()
    return normalized in DYNAMIC_FACT_TOKENS or any(
        token in normalized for token in DYNAMIC_FACT_TOKENS if len(token) > 1
    )
