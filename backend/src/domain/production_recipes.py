from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.exceptions import ValidationException
from src.domain.enums import ProductionMode


class MediaStrategy(StrEnum):
    STATIC_CARD = "static_card"
    ONLINE_ASSET = "online_asset"
    UPLOADED_ASSET = "uploaded_asset"
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"


class MediaPlan(BaseModel):
    """Typed, per-shot execution contract persisted in a job snapshot."""

    model_config = ConfigDict(extra="forbid")

    strategy: MediaStrategy
    reference_asset_ids: list[str] = Field(default_factory=list)
    source_asset_id: str | None = None
    image_workflow_id: str | None = None
    video_workflow_id: str | None = None
    continuity_inputs: dict[str, Any] = Field(default_factory=dict)
    fallback_policy: Literal["error"] = "error"
    cost_tier: Literal["low", "medium", "high"] = "low"

    @model_validator(mode="after")
    def validate_required_inputs(self) -> MediaPlan:
        if self.strategy == MediaStrategy.UPLOADED_ASSET and not self.source_asset_id:
            raise ValueError("uploaded_asset 必须指定 source_asset_id")
        if self.strategy in {MediaStrategy.IMAGE_TO_IMAGE, MediaStrategy.IMAGE_TO_VIDEO}:
            if not self.reference_asset_ids and not self.source_asset_id:
                raise ValueError(f"{self.strategy.value} 必须指定参考素材")
        return self


class ProductionRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_id: str
    mode: ProductionMode
    name: str
    description: str
    cost_tier: Literal["low", "medium", "high"]
    required_capabilities: frozenset[str] = frozenset()
    requires_reference_assets: bool = False
    allowed_strategies: frozenset[MediaStrategy]
    default_strategy: MediaStrategy


class ProductionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    mode: ProductionMode
    recipe: ProductionRecipe
    scene_plans: dict[str, MediaPlan] = Field(default_factory=dict)
    planning_rules: dict[str, MediaStrategy] = Field(default_factory=dict)
    default_reference_asset_ids: list[str] = Field(default_factory=list)


RECIPES: dict[str, ProductionRecipe] = {
    item.recipe_id: item
    for item in (
        ProductionRecipe(
            recipe_id="knowledge_quick",
            mode=ProductionMode.KNOWLEDGE,
            name="快速模板科普",
            description="信息卡或 AI 配图配合模板。",
            cost_tier="low",
            allowed_strategies=frozenset(
                {MediaStrategy.STATIC_CARD, MediaStrategy.TEXT_TO_IMAGE}
            ),
            default_strategy=MediaStrategy.STATIC_CARD,
        ),
        ProductionRecipe(
            recipe_id="knowledge_real_material",
            mode=ProductionMode.KNOWLEDGE,
            name="真实素材科普",
            description="在线或已上传素材配合模板。",
            cost_tier="low",
            required_capabilities=frozenset({"material"}),
            allowed_strategies=frozenset(
                {MediaStrategy.ONLINE_ASSET, MediaStrategy.UPLOADED_ASSET}
            ),
            default_strategy=MediaStrategy.ONLINE_ASSET,
        ),
        ProductionRecipe(
            recipe_id="knowledge_dynamic",
            mode=ProductionMode.KNOWLEDGE,
            name="AI 动态科普",
            description="文生视频或关键图后图生视频。",
            cost_tier="high",
            required_capabilities=frozenset({"video"}),
            allowed_strategies=frozenset(
                {MediaStrategy.TEXT_TO_VIDEO, MediaStrategy.IMAGE_TO_VIDEO}
            ),
            default_strategy=MediaStrategy.TEXT_TO_VIDEO,
        ),
        ProductionRecipe(
            recipe_id="knowledge_smart_mix",
            mode=ProductionMode.KNOWLEDGE,
            name="智能混合",
            description="按分镜语义选择信息卡、AI 图片或真实素材。",
            cost_tier="medium",
            required_capabilities=frozenset({"image", "material"}),
            allowed_strategies=frozenset(
                {
                    MediaStrategy.STATIC_CARD,
                    MediaStrategy.TEXT_TO_IMAGE,
                    MediaStrategy.IMAGE_TO_VIDEO,
                    MediaStrategy.ONLINE_ASSET,
                    MediaStrategy.UPLOADED_ASSET,
                }
            ),
            default_strategy=MediaStrategy.TEXT_TO_IMAGE,
        ),
        ProductionRecipe(
            recipe_id="commerce_product_showcase",
            mode=ProductionMode.COMMERCE,
            name="商品展示",
            description="真实商品素材与确定性模板运动。",
            cost_tier="low",
            requires_reference_assets=True,
            allowed_strategies=frozenset({MediaStrategy.UPLOADED_ASSET}),
            default_strategy=MediaStrategy.UPLOADED_ASSET,
        ),
        ProductionRecipe(
            recipe_id="commerce_lifestyle",
            mode=ProductionMode.COMMERCE,
            name="场景种草",
            description="商品参考图生成场景，事实镜头继续使用真实商品素材。",
            cost_tier="medium",
            required_capabilities=frozenset({"image"}),
            requires_reference_assets=True,
            allowed_strategies=frozenset(
                {MediaStrategy.UPLOADED_ASSET, MediaStrategy.IMAGE_TO_IMAGE}
            ),
            default_strategy=MediaStrategy.IMAGE_TO_IMAGE,
        ),
        ProductionRecipe(
            recipe_id="commerce_dynamic_demo",
            mode=ProductionMode.COMMERCE,
            name="动态演示",
            description="商品参考图或首帧驱动主视觉与使用过程。",
            cost_tier="high",
            required_capabilities=frozenset({"video"}),
            requires_reference_assets=True,
            allowed_strategies=frozenset(
                {MediaStrategy.UPLOADED_ASSET, MediaStrategy.IMAGE_TO_VIDEO}
            ),
            default_strategy=MediaStrategy.IMAGE_TO_VIDEO,
        ),
        ProductionRecipe(
            recipe_id="commerce_ugc_mix",
            mode=ProductionMode.COMMERCE,
            name="UGC 混剪",
            description="上传真人实拍与真实商品素材混剪。",
            cost_tier="medium",
            requires_reference_assets=True,
            allowed_strategies=frozenset({MediaStrategy.UPLOADED_ASSET}),
            default_strategy=MediaStrategy.UPLOADED_ASSET,
        ),
        ProductionRecipe(
            recipe_id="drama_reference_i2v",
            mode=ProductionMode.DRAMA,
            name="参考图动态短剧",
            description="审批参考资产约束关键帧，并逐镜生成动态 clip。",
            cost_tier="high",
            required_capabilities=frozenset({"image", "video"}),
            requires_reference_assets=True,
            allowed_strategies=frozenset({MediaStrategy.IMAGE_TO_VIDEO}),
            default_strategy=MediaStrategy.IMAGE_TO_VIDEO,
        ),
        ProductionRecipe(
            recipe_id="drama_animatic",
            mode=ProductionMode.DRAMA,
            name="动态漫 / 低成本预演",
            description="显式低成本预演，使用有限 I2V 或模板运动。",
            cost_tier="medium",
            allowed_strategies=frozenset(
                {MediaStrategy.IMAGE_TO_VIDEO, MediaStrategy.UPLOADED_ASSET}
            ),
            default_strategy=MediaStrategy.UPLOADED_ASSET,
        ),
    )
}

DEFAULT_RECIPE_IDS = {
    # Tasks created by older clients omit recipe_id. Keep that implicit path
    # cheap and deterministic; the current UI explicitly selects recommended
    # defaults such as knowledge_smart_mix and drama_reference_i2v.
    ProductionMode.KNOWLEDGE: "knowledge_quick",
    ProductionMode.COMMERCE: "commerce_product_showcase",
    ProductionMode.DRAMA: "drama_animatic",
}


def recipes_for_mode(mode: ProductionMode | str) -> list[ProductionRecipe]:
    normalized = ProductionMode(mode)
    return [item for item in RECIPES.values() if item.mode == normalized]


def resolve_recipe(mode: ProductionMode | str, recipe_id: str | None) -> ProductionRecipe:
    normalized = ProductionMode(mode)
    selected = recipe_id or DEFAULT_RECIPE_IDS[normalized]
    recipe = RECIPES.get(selected)
    if recipe is None or recipe.mode != normalized:
        raise ValidationException(f"Recipe {selected} 不适用于 {normalized.value} 模式。")
    return recipe


def _knowledge_rules(recipe_id: str) -> dict[str, MediaStrategy]:
    if recipe_id == "knowledge_smart_mix":
        return {
            "data": MediaStrategy.STATIC_CARD,
            "comparison": MediaStrategy.STATIC_CARD,
            "timeline": MediaStrategy.STATIC_CARD,
            "quote": MediaStrategy.STATIC_CARD,
            "process": MediaStrategy.TEXT_TO_IMAGE,
            "concept": MediaStrategy.TEXT_TO_IMAGE,
            "example": MediaStrategy.ONLINE_ASSET,
            "b_roll": MediaStrategy.ONLINE_ASSET,
        }
    return {}


def compile_production_plan(
    mode: ProductionMode | str,
    settings: dict[str, Any],
    scenes: list[Any],
    *,
    default_reference_asset_ids: list[str] | None = None,
) -> ProductionPlan:
    normalized = ProductionMode(mode)
    recipe = resolve_recipe(normalized, settings.get("recipe_id"))
    rules = _knowledge_rules(recipe.recipe_id)
    overrides = settings.get("media_plan_overrides") or {}
    if not isinstance(overrides, dict):
        raise ValidationException("media_plan_overrides 必须是按 Scene/Shot ID 索引的对象。")
    scene_plans: dict[str, MediaPlan] = {}
    references = list(default_reference_asset_ids or [])
    for scene in scenes:
        scene_id = str(scene.get("id") if isinstance(scene, dict) else scene.id)
        role = str(
            scene.get("visual_role", "concept")
            if isinstance(scene, dict)
            else getattr(scene, "visual_role", "concept")
        )
        metadata = (
            scene.get("production_metadata") or {}
            if isinstance(scene, dict)
            else getattr(scene, "production_metadata", None) or {}
        )
        raw = overrides.get(scene_id) or metadata.get("media_plan")
        if raw:
            plan = MediaPlan.model_validate(raw)
        else:
            strategy = rules.get(role, recipe.default_strategy)
            source_asset_id = settings.get("source_asset_id")
            plan = MediaPlan(
                strategy=strategy,
                source_asset_id=source_asset_id if strategy == MediaStrategy.UPLOADED_ASSET else None,
                reference_asset_ids=(
                    references
                    if strategy in {MediaStrategy.IMAGE_TO_IMAGE, MediaStrategy.IMAGE_TO_VIDEO}
                    else []
                ),
                image_workflow_id=settings.get("image_workflow_id"),
                video_workflow_id=settings.get("video_workflow_id"),
                cost_tier=recipe.cost_tier,
            )
        if plan.strategy not in recipe.allowed_strategies:
            raise ValidationException(
                f"Scene/Shot {scene_id} 的 {plan.strategy.value} 不属于 Recipe {recipe.name}。"
            )
        scene_plans[scene_id] = plan
    return ProductionPlan(
        mode=normalized,
        recipe=recipe,
        scene_plans=scene_plans,
        planning_rules=rules,
        default_reference_asset_ids=references,
    )


def missing_capabilities(plan: ProductionPlan, providers: dict[str, Any]) -> list[str]:
    required = set(plan.recipe.required_capabilities)
    for media_plan in plan.scene_plans.values():
        if media_plan.strategy == MediaStrategy.ONLINE_ASSET:
            required.add("material")
        elif media_plan.strategy in {MediaStrategy.TEXT_TO_IMAGE, MediaStrategy.IMAGE_TO_IMAGE}:
            required.add("image")
        elif media_plan.strategy in {MediaStrategy.TEXT_TO_VIDEO, MediaStrategy.IMAGE_TO_VIDEO}:
            required.add("video")
    return sorted(item for item in required if not providers.get(item))
