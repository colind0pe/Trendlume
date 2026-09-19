from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationException
from src.domain.enums import CreativeAngle
from src.models.creative_plan import CreativePlanModel
from src.models.product import ProductModel
from src.services.commerce_planning_service import CommercePlanningService


@dataclass(frozen=True, slots=True)
class CommerceTaskContext:
    product_id: str
    creative_plan_id: str | None
    creative_angle: CreativeAngle
    creative_plan_snapshot: dict | None = None


async def resolve_commerce_task_context(
    session: AsyncSession,
    *,
    product_id: str | None,
    creative_plan_id: str | None,
    creative_angle: str | CreativeAngle | None,
    include_plan_snapshot: bool = False,
) -> CommerceTaskContext:
    """Validate the Commerce ownership fields shared by task create/update."""
    if not product_id:
        raise ValidationException("Commerce 生产任务必须选择商品。")
    product = await session.get(ProductModel, str(product_id))
    if not product:
        raise ValidationException("所选商品不存在，请先在商品库中创建商品。")
    try:
        angle = CreativeAngle(str(creative_angle or CreativeAngle.DIRECT.value))
    except ValueError as exc:
        raise ValidationException("不支持的商业创意角度。") from exc

    plan = None
    if creative_plan_id:
        plan = await session.get(CreativePlanModel, str(creative_plan_id))
        if not plan or plan.product_id != product.id:
            raise ValidationException("所选 Creative Plan 不属于当前商品。")
        if plan.status not in {"selected", "variant"}:
            raise ValidationException("请先选择 Creative Plan，再进入 storyboard/media 生产。")
        try:
            angle = CreativeAngle(plan.angle)
        except ValueError as exc:
            raise ValidationException("Creative Plan 的创意角度无效。") from exc

    snapshot = None
    if include_plan_snapshot and plan:
        snapshot = await CommercePlanningService(session).plan_payload(plan.id)
    return CommerceTaskContext(
        product_id=product.id,
        creative_plan_id=plan.id if plan else None,
        creative_angle=angle,
        creative_plan_snapshot=snapshot,
    )
