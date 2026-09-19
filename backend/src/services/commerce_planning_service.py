from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.commerce import CREATIVE_ANGLE_LABELS, is_dynamic_fact_field
from src.domain.enums import CreativeAngle, VisualRole
from src.models.creative_plan import CreativePlanModel
from src.models.product import ProductModel
from src.schemas.creative_plan import (
    CreativePlanGenerateRequest,
    CreativePlanResponse,
    CreativeSceneOutline,
)
from src.schemas.product import ProductTruthSheet
from src.services.product_service import ProductService

PLAN_DIRECTIONS = (
    {
        "angle": CreativeAngle.DIRECT.value,
        "hook": "先把商品本身看清楚，再决定它是否适合你。",
        "audience": "正在快速了解商品信息的潜在购买者",
        "core_message": "用真实商品素材和已确认事实，降低第一次了解商品的成本。",
    },
    {
        "angle": CreativeAngle.PAIN_POINT.value,
        "hook": "如果你正在反复比较，先看这件商品能不能对应你的需要。",
        "audience": "带着明确问题寻找解决方案的潜在购买者",
        "core_message": "从真实需求切入，只解释商品事实能够支持的价值。",
    },
    {
        "angle": CreativeAngle.USE_CASE.value,
        "hook": "把商品放回真实使用场景，判断它是否适合你的日常。",
        "audience": "希望确认使用场景和适配关系的潜在购买者",
        "core_message": "用克制的场景表达帮助观众建立适配判断，不替商品作无证据承诺。",
    },
)


def _text(value: Any, limit: int = 1000) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


class CommercePlanningService:
    """Persist reviewable Commerce plans without invoking media providers."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.products = ProductService(session)

    async def _product(self, product_id: str) -> ProductModel:
        return await self.products.get_product(product_id)

    @staticmethod
    def _truth(product: ProductModel) -> ProductTruthSheet:
        try:
            truth = ProductTruthSheet.model_validate(product.truth_sheet or {})
        except Exception as exc:
            raise ValidationException("商品 Truth Sheet 无法校验，请先修正商品事实。") from exc
        if truth.product_id and truth.product_id != product.id:
            raise ValidationException("商品 Truth Sheet 与商品 ID 不一致。")
        truth.product_id = product.id
        return truth

    @staticmethod
    def _fact_snapshot(product: ProductModel, truth: ProductTruthSheet) -> dict[str, Any]:
        facts = [fact.model_dump(mode="json") for fact in truth.facts]
        dynamic = {
            fact.field: {
                "value": fact.value,
                "source_ref": fact.source_ref,
                "certainty": fact.certainty,
                "user_confirmed": fact.user_confirmed,
            }
            for fact in truth.facts
            if is_dynamic_fact_field(fact.field)
        }
        return {
            "captured_at": datetime.now(UTC).isoformat(),
            "truth_sheet_version": truth.version,
            "product_fields": {
                "title": product.title,
                "brand": product.brand,
                "price": product.price,
                "currency": product.currency,
            },
            "facts": facts,
            "dynamic_facts": dynamic,
            "product_asset_ids": [
                asset.id for asset in product.assets if asset.asset_id
            ],
            "confirmed_by_user": False,
        }

    @staticmethod
    def _claims(truth: ProductTruthSheet) -> list[dict[str, Any]]:
        dynamic_fact_ids = {
            fact.id for fact in truth.facts if is_dynamic_fact_field(fact.field)
        }
        claims: list[dict[str, Any]] = []
        for claim in [*truth.selling_points, *truth.numerical_claims]:
            if claim.certainty == "uncertain" or not claim.evidence_refs:
                continue
            if dynamic_fact_ids.intersection(claim.evidence_refs):
                continue
            claims.append(
                {
                    "id": claim.id,
                    "text": claim.text,
                    "claim_type": claim.claim_type,
                    "evidence_refs": list(claim.evidence_refs),
                }
            )
        return claims[:6]

    @staticmethod
    def _outline(
        product: ProductModel,
        *,
        hook: str,
        claims: list[dict[str, Any]],
        cta: str,
    ) -> list[dict[str, Any]]:
        title = _text(product.title, 80)
        first_claim = claims[0] if claims else None
        second_claim = claims[1] if len(claims) > 1 else first_claim
        outline = [
            CreativeSceneOutline(
                sequence_index=0,
                beat="Hook",
                visual="中性留白与简洁排版，先提出判断问题，不生成商品外观或价格文字。",
                narration=hook,
                visual_role=VisualRole.CONTEXT,
                asset_strategy="deterministic_layout",
            ),
            CreativeSceneOutline(
                sequence_index=1,
                beat="Product reveal",
                visual=f"使用商品库中的原始商品资产展示 {title}，只做裁切、缩放和轻微 Ken Burns。",
                narration=f"先看清楚这件商品：{title}。",
                visual_role=VisualRole.PRODUCT_SHOT,
                asset_strategy="product_asset",
            ),
            CreativeSceneOutline(
                sequence_index=2,
                beat="Core value",
                visual="用确定性的版式、背景和局部动作承载核心信息，不重绘商品主体。",
                narration=(
                    f"目前可以确认的重点是：{first_claim['text']}。"
                    if first_claim
                    else "只表达商品资料中已经确认的信息，不补写未经核实的效果。"
                ),
                visual_role=VisualRole.BENEFIT,
                claim_refs=[first_claim["id"]] if first_claim else [],
                asset_strategy="deterministic_layout",
            ),
            CreativeSceneOutline(
                sequence_index=3,
                beat="Use case",
                visual="使用中性环境、留白、裁切或缩放表达使用语境，不生成新的商品细节。",
                narration=f"把它放回真实场景，再判断 {title} 是否适合你的需要。",
                visual_role=VisualRole.CONTEXT,
                asset_strategy="deterministic_layout",
            ),
            CreativeSceneOutline(
                sequence_index=4,
                beat="Proof point",
                visual="回到真实商品资产或事实卡，以简洁叠加呈现可追溯依据。",
                narration=(
                    f"另一个可以核对的重点是：{second_claim['text']}。"
                    if second_claim
                    else "需要更多信息时，请回到商品事实卡核对来源。"
                ),
                visual_role=VisualRole.PROOF,
                claim_refs=[second_claim["id"]] if second_claim else [],
                asset_strategy="product_asset" if second_claim else "deterministic_layout",
            ),
            CreativeSceneOutline(
                sequence_index=5,
                beat="CTA",
                visual="使用真实商品资产配合克制的了解入口，不加入未确认价格、折扣或稀缺性文案。",
                narration=cta,
                visual_role=VisualRole.CTA,
                asset_strategy="product_asset",
            ),
        ]
        return [item.model_dump(mode="json") for item in outline]

    @staticmethod
    def _plan_snapshot(plan: CreativePlanModel) -> dict[str, Any]:
        return CreativePlanResponse.model_validate(plan).model_dump(mode="json")

    async def list_plans(self, product_id: str) -> list[CreativePlanModel]:
        await self._product(product_id)
        result = await self.session.scalars(
            select(CreativePlanModel)
            .where(CreativePlanModel.product_id == product_id)
            .order_by(CreativePlanModel.created_at.desc(), CreativePlanModel.variant_index)
        )
        return list(result.all())

    async def get_plan(self, plan_id: str, product_id: str | None = None) -> CreativePlanModel:
        plan = await self.session.get(CreativePlanModel, plan_id)
        if not plan or (product_id and plan.product_id != product_id):
            raise NotFoundException("CreativePlan", plan_id)
        return plan

    async def generate_plans(
        self,
        product_id: str,
        request: CreativePlanGenerateRequest | None = None,
    ) -> list[CreativePlanModel]:
        request = request or CreativePlanGenerateRequest()
        product = await self._product(product_id)
        truth = self._truth(product)
        claims = self._claims(truth)
        snapshot = self._fact_snapshot(product, truth)
        existing = list(
            (
                await self.session.scalars(
                    select(CreativePlanModel).where(
                        CreativePlanModel.product_id == product_id,
                        CreativePlanModel.status.in_(["draft", "selected"]),
                    )
                )
            ).all()
        )
        for plan in existing:
            plan.status = "archived"

        created: list[CreativePlanModel] = []
        for index, direction in enumerate(PLAN_DIRECTIONS[: request.count], start=1):
            angle = direction["angle"]
            title = _text(product.title, 80)
            hook = f"{direction['hook']}"
            if angle == CreativeAngle.DIRECT.value:
                hook = f"{title}：{hook}"
            audience = _text(request.audience or direction["audience"], 500)
            objective = _text(request.objective or direction["core_message"], 500)
            cta = f"如果它符合你的需求，可以回到商品页核对信息，再决定是否了解 {title}。"
            plan = CreativePlanModel(
                id=f"cplan_{uuid4().hex[:12]}",
                product_id=product.id,
                status="draft",
                variant_label=f"Plan {index}",
                variant_index=index,
                angle=angle,
                hook=hook,
                audience=audience,
                core_message=objective,
                claims=deepcopy(claims),
                scene_outline=self._outline(product, hook=hook, claims=claims, cta=cta),
                cta=cta,
                truth_sheet_version=truth.version,
                fact_snapshot=deepcopy(snapshot),
            )
            self.session.add(plan)
            created.append(plan)
        await self.session.commit()
        return [await self.get_plan(plan.id, product_id) for plan in created]

    async def select_plan(self, product_id: str, plan_id: str) -> CreativePlanModel:
        target = await self.get_plan(plan_id, product_id)
        if target.status == "archived":
            raise ValidationException("已归档的 Creative Plan 不能被选择，请重新生成方案。")
        plans = await self.list_plans(product_id)
        selected_at = datetime.now(UTC)
        for plan in plans:
            if plan.id == target.id:
                plan.status = "selected"
                plan.selected_at = selected_at
            elif plan.status == "selected":
                plan.status = "draft"
                plan.selected_at = None
        await self.session.commit()
        return await self.get_plan(target.id, product_id)

    async def duplicate_plan(
        self,
        product_id: str,
        plan_id: str,
        variant_label: str | None = None,
    ) -> CreativePlanModel:
        source = await self.get_plan(plan_id, product_id)
        if source.status != "selected":
            raise ValidationException("请先选择一个 Creative Plan，再复制成 Variant。")
        max_index = await self.session.scalar(
            select(func.max(CreativePlanModel.variant_index)).where(
                CreativePlanModel.product_id == product_id
            )
        )
        variant = CreativePlanModel(
            id=f"cplan_{uuid4().hex[:12]}",
            product_id=source.product_id,
            source_plan_id=source.id,
            status="variant",
            variant_label=variant_label or f"Variant {(max_index or source.variant_index) + 1}",
            variant_index=int(max_index or source.variant_index) + 1,
            angle=source.angle,
            hook=source.hook,
            audience=source.audience,
            core_message=source.core_message,
            claims=deepcopy(source.claims),
            scene_outline=deepcopy(source.scene_outline),
            cta=source.cta,
            truth_sheet_version=source.truth_sheet_version,
            fact_snapshot=deepcopy(source.fact_snapshot),
        )
        self.session.add(variant)
        await self.session.commit()
        return await self.get_plan(variant.id, product_id)

    async def confirm_facts(self, product_id: str, plan_id: str) -> CreativePlanModel:
        plan = await self.get_plan(plan_id, product_id)
        product = await self._product(product_id)
        truth = self._truth(product)
        snapshot = self._fact_snapshot(product, truth)
        snapshot["confirmed_by_user"] = True
        snapshot["confirmed_at"] = datetime.now(UTC).isoformat()
        for value in (snapshot.get("dynamic_facts") or {}).values():
            value["user_confirmed"] = True
        plan.fact_snapshot = snapshot
        plan.truth_sheet_version = truth.version
        await self.session.commit()
        return await self.get_plan(plan_id, product_id)

    async def plan_payload(self, plan_id: str) -> dict[str, Any]:
        plan = await self.get_plan(plan_id)
        return self._plan_snapshot(plan)

    @staticmethod
    def plan_label(plan: CreativePlanModel) -> str:
        return f"{plan.variant_label} · {CREATIVE_ANGLE_LABELS.get(plan.angle, plan.angle)}"
