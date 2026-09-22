from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationException
from src.domain.production_recipes import (
    compile_production_plan,
    media_strategy_for_content_mode,
    missing_capabilities,
    resolve_recipe,
)
from src.models.asset import AssetModel
from src.models.drama import DramaCharacterModel, DramaLocationModel, DramaPropModel
from src.models.product import ProductAssetModel, ProductModel
from src.models.production_context import ProductionContextSnapshotModel
from src.models.project import ProjectAssetBindingModel, ProjectModel
from src.models.task import TaskModel
from src.models.task_detail import (
    DramaTaskDialogueLineModel,
    DramaTaskSceneModel,
    DramaTaskShotModel,
)
from src.services.provider_manager import ProviderManager


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


class ProductionContextCompiler:
    """The only boundary that turns editable project/task state into execution input."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def readiness(self, task_id: str) -> dict[str, Any]:
        task = await self.session.get(TaskModel, task_id)
        if task is None:
            raise ValidationException("任务不存在。")
        project = await self.session.get(ProjectModel, task.project_id)
        if project is None:
            raise ValidationException("任务所属项目不存在。")
        checks: list[dict[str, str]] = []

        def add(key: str, label: str, passed: bool, message: str) -> None:
            checks.append(
                {
                    "key": key,
                    "label": label,
                    "status": "pass" if passed else "error",
                    "message": message,
                }
            )

        approved = task.editorial_status == "approved"
        add("approval", "内容审批", approved, "Task 已审批。" if approved else "请先审批 Task。")
        has_template = project.template is not None
        add(
            "template",
            "项目模板",
            has_template,
            "项目模板已配置。" if has_template else "请先配置项目模板。",
        )
        detail = self._detail(project, task)
        recipe = resolve_recipe(project.mode, (task.generation_settings or {}).get("recipe_id"))
        add(
            "recipe",
            "生产方案",
            True,
            f"已选择：{recipe.name}（{recipe.cost_tier} 成本）。",
        )
        if project.mode == "knowledge":
            has_topic = bool(detail.topic.strip())
            add(
                "knowledge_topic",
                "知识主题",
                has_topic,
                "知识主题已填写。" if has_topic else "请填写知识主题。",
            )
        elif project.mode == "commerce":
            products = list(
                (
                    await self.session.scalars(
                        select(ProductModel).where(ProductModel.project_id == project.id)
                    )
                ).all()
            )
            product = products[0] if len(products) == 1 else None
            has_product = product is not None and bool(product.title.strip())
            add(
                "commerce_product",
                "主商品",
                has_product,
                "主商品已配置。" if has_product else "请配置唯一主商品。",
            )
            asset_count = (
                0
                if product is None
                else int(
                    (
                        await self.session.scalar(
                            select(func.count(ProductAssetModel.id)).where(
                                ProductAssetModel.product_id == product.id
                            )
                        )
                    )
                    or 0
                )
            )
            add(
                "commerce_assets",
                "商品素材",
                asset_count > 0,
                f"已绑定 {asset_count} 个商品素材。"
                if asset_count
                else "请至少绑定一个商品图片或视频。",
            )
            dynamic_facts = (product.truth_sheet or {}).get("dynamic_facts", []) if product else []
            stale_facts = [
                item for item in dynamic_facts
                if isinstance(item, dict) and not (item.get("confirmed") or item.get("verified_at"))
            ]
            add(
                "commerce_dynamic_facts",
                "动态商品事实",
                not stale_facts,
                "价格与活动事实已确认。" if not stale_facts else "请确认价格或活动等动态事实。",
            )
        else:
            groups = []
            for key, label, model in (
                ("characters", "人物", DramaCharacterModel),
                ("locations", "地点", DramaLocationModel),
                ("props", "道具", DramaPropModel),
            ):
                rows = list(
                    (
                        await self.session.scalars(
                            select(model).where(model.project_id == project.id)
                        )
                    ).all()
                )
                groups.extend(rows)
                add(
                    f"drama_{key}",
                    label,
                    bool(rows),
                    f"已配置 {len(rows)} 个{label}。"
                    if rows
                    else f"请至少配置一个{label}。",
                )
            unapproved = [item.name for item in groups if item.approval_status != "approved"]
            add(
                "drama_approval",
                "Drama 资源审批",
                not unapproved,
                "Drama 资源已审批。"
                if not unapproved
                else "请审批：" + "、".join(unapproved),
            )
            if recipe.recipe_id == "drama_reference_i2v":
                missing_references = [
                    item.name for item in groups if not self._drama_reference_asset_ids(item)
                ]
                add(
                    "drama_reference_assets",
                    "Drama 参考素材",
                    not missing_references,
                    "人物、地点和道具参考素材已绑定。"
                    if not missing_references
                    else "请为以下资源绑定参考素材：" + "、".join(missing_references),
                )
                approved_scenes = list((await self.session.scalars(
                    select(DramaTaskSceneModel).where(
                        DramaTaskSceneModel.task_id == task.id,
                        DramaTaskSceneModel.approval_status == "approved",
                    )
                )).all())
                approved_scene_ids = [item.id for item in approved_scenes]
                approved_shots = list((await self.session.scalars(
                    select(DramaTaskShotModel).where(
                        DramaTaskShotModel.scene_id.in_(approved_scene_ids),
                        DramaTaskShotModel.approval_status == "approved",
                    )
                )).all()) if approved_scene_ids else []
                add(
                    "drama_approved_shots",
                    "已审批逐镜",
                    bool(approved_shots),
                    f"已审批 {len(approved_shots)} 个 Shot；正式 Recipe 会逐镜生成动态 clip。"
                    if approved_shots
                    else "请先完成剧本、Scene 和 Shot 审核；关键帧不会作为最终镜头。",
                )
                add(
                    "drama_audio_boundary",
                    "音画时间线",
                    True,
                    "speaker、shot 和时长会进入快照；当前执行器按 Shot 混合台词配音，逐角色独立声轨与原声审计尚未实现。",
                )
        providers = await ProviderManager(self.session).capture_snapshot(
            search_provider_id=(task.generation_settings or {}).get("search_provider_id"),
            material_provider_id=(task.generation_settings or {}).get("material_provider_id"),
        )
        required_capabilities = set(recipe.required_capabilities)
        requested_strategy = media_strategy_for_content_mode(
            (task.generation_settings or {}).get("content_mode")
        )
        if requested_strategy is not None and requested_strategy.value != "online_asset":
            # Recipe-level mixed-media requirements must not override the
            # user's explicit generated-image/content-source selection.
            required_capabilities.discard("material")
        for capability in sorted(required_capabilities):
            configured = bool(providers.get(capability))
            add(
                f"provider_{capability}",
                f"{capability} Provider",
                configured,
                f"{capability} Provider 已快照。" if configured
                else f"Recipe {recipe.name} 需要可用的 {capability} Provider。",
            )
        add(
            "estimated_cost",
            "预计操作成本",
            True,
            {"low": "主要为确定性处理或低成本素材操作。", "medium": "包含部分生成或素材获取操作。", "high": "包含逐镜图像/视频生成等昂贵操作。"}[recipe.cost_tier],
        )
        return {
            "task_id": task.id,
            "mode": project.mode,
            "ready": all(item["status"] == "pass" for item in checks),
            "checks": checks,
        }

    async def compile(
        self,
        task_id: str,
        *,
        provider_snapshot: dict[str, Any],
        workflow_config: dict[str, Any] | None = None,
    ) -> ProductionContextSnapshotModel:
        task = await self.session.get(TaskModel, task_id)
        if task is None:
            raise ValidationException("任务不存在。")
        project = await self.session.get(ProjectModel, task.project_id)
        if project is None:
            raise ValidationException("任务所属项目不存在。")

        detail = self._detail(project, task)
        asset_rows = (
            await self.session.execute(
                select(ProjectAssetBindingModel, AssetModel)
                .join(AssetModel, AssetModel.id == ProjectAssetBindingModel.asset_id)
                .where(ProjectAssetBindingModel.project_id == project.id)
            )
        ).all()
        mode_context: dict[str, Any]
        planning_units: list[Any] = []
        reference_asset_ids: list[str] = []
        if project.mode == "knowledge":
            mode_context = self._columns(project.knowledge_profile)
            planning_units = list(task.scenes or [])
            reference_asset_ids = [asset.id for _, asset in asset_rows]
        elif project.mode == "commerce":
            products = list(
                (
                    await self.session.scalars(
                        select(ProductModel).where(ProductModel.project_id == project.id)
                    )
                ).all()
            )
            if len(products) != 1:
                raise ValidationException("Commerce Project 必须且只能配置一个主商品。")
            mode_context = {
                "profile": self._columns(project.commerce_profile),
                "product": self._columns(products[0]),
            }
            product_assets = list((await self.session.scalars(
                select(ProductAssetModel).where(ProductAssetModel.product_id == products[0].id)
            )).all())
            reference_asset_ids = [item.asset_id for item in product_assets if item.asset_id]
            planning_units = list(task.scenes or [])
        elif project.mode == "drama":
            characters = list(
                (
                    await self.session.scalars(
                        select(DramaCharacterModel).where(
                            DramaCharacterModel.project_id == project.id
                        )
                    )
                ).all()
            )
            locations = list(
                (
                    await self.session.scalars(
                        select(DramaLocationModel).where(
                            DramaLocationModel.project_id == project.id
                        )
                    )
                ).all()
            )
            props = list(
                (
                    await self.session.scalars(
                        select(DramaPropModel).where(DramaPropModel.project_id == project.id)
                    )
                ).all()
            )
            unapproved = [
                item.name
                for item in [*characters, *locations, *props]
                if item.approval_status != "approved"
            ]
            if unapproved:
                raise ValidationException(
                    "Drama 人物、地点和道具必须先通过审批：" + "、".join(unapproved)
                )
            drama_scenes = list((await self.session.scalars(
                select(DramaTaskSceneModel).where(DramaTaskSceneModel.task_id == task.id)
            )).all())
            scene_ids = [scene.id for scene in drama_scenes]
            drama_shots = list((await self.session.scalars(
                select(DramaTaskShotModel).where(DramaTaskShotModel.scene_id.in_(scene_ids))
            )).all()) if scene_ids else []
            shot_ids = [shot.id for shot in drama_shots]
            drama_dialogue = list((await self.session.scalars(
                select(DramaTaskDialogueLineModel).where(
                    DramaTaskDialogueLineModel.shot_id.in_(shot_ids)
                )
            )).all()) if shot_ids else []
            project_location_ids = {item.id for item in locations}
            project_character_ids = {item.id for item in characters}
            project_prop_ids = {item.id for item in props}
            episode_continuity = getattr(detail, "continuity_data", {}) or {}
            selected_character_ids = set(episode_continuity.get("character_ids", []))
            selected_location_ids = set(episode_continuity.get("location_ids", []))
            selected_prop_ids = set(episode_continuity.get("prop_ids", []))
            if (
                not selected_character_ids.issubset(project_character_ids)
                or not selected_location_ids.issubset(project_location_ids)
                or not selected_prop_ids.issubset(project_prop_ids)
            ):
                raise ValidationException("Drama Task 不能引用其他 Project 的连续性资源。")
            if any(
                scene.location_id and scene.location_id not in project_location_ids
                for scene in drama_scenes
            ) or any(
                shot.location_id and shot.location_id not in project_location_ids
                for shot in drama_shots
            ) or any(
                character_id not in project_character_ids
                for shot in drama_shots for character_id in shot.character_ids
            ):
                raise ValidationException("Drama Scene/Shot 不能引用其他 Project 的资源。")
            if any(item.approval_status != "approved" for item in [*drama_scenes, *drama_shots]):
                raise ValidationException("Drama Scene 和 Shot 必须先通过审批。")
            mode_context = {
                "profile": self._columns(project.drama_profile),
                "style_guide": self._columns(project.drama_style_guide),
                "characters": [self._columns(item) for item in characters],
                "locations": [self._columns(item) for item in locations],
                "props": [self._columns(item) for item in props],
                "scenes": [self._columns(item) for item in drama_scenes],
                "shots": [self._columns(item) for item in drama_shots],
                "dialogue": [self._columns(item) for item in drama_dialogue],
            }
            planning_units = [self._drama_shot_unit(item) for item in drama_shots]
            reference_asset_ids = sorted({
                asset_id
                for item in [*characters, *locations, *props]
                for asset_id in self._drama_reference_asset_ids(item)
            })
            bound_asset_ids = {asset.id for _, asset in asset_rows}
            if not set(reference_asset_ids).issubset(bound_asset_ids):
                raise ValidationException("Drama 参考素材必须属于当前 Project。")
        else:
            raise ValidationException("项目生产模式无效。")

        production_plan = compile_production_plan(
            project.mode,
            task.generation_settings or {},
            planning_units,
            default_reference_asset_ids=reference_asset_ids,
        )
        missing = missing_capabilities(production_plan, provider_snapshot)
        if missing:
            raise ValidationException(
                f"Recipe {production_plan.recipe.name} 缺少 Provider 能力：" + "、".join(missing)
            )
        payload = _stable(
            {
                "schema_version": 2,
                "mode": project.mode,
                "production_plan": production_plan.model_dump(mode="json"),
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "aspect_ratio": project.aspect_ratio,
                    "status": project.status,
                    "default_production_settings": project.default_production_settings,
                },
                "project_profile": mode_context,
                "project_template": self._columns(project.template),
                "project_assets": [
                    {
                        "binding": self._columns(binding),
                        "asset": self._columns(asset),
                    }
                    for binding, asset in asset_rows
                ],
                "task": {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "editorial_status": task.editorial_status,
                    "generation_settings": task.generation_settings,
                    "publishing_settings": task.publishing_settings,
                    "detail": self._columns(detail),
                },
                "providers": provider_snapshot,
                "workflows": workflow_config or {},
            }
        )
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        snapshot = ProductionContextSnapshotModel(
            task_id=task.id,
            project_id=project.id,
            mode=project.mode,
            context_hash=hashlib.sha256(encoded).hexdigest(),
            context_payload=payload,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    @staticmethod
    def _detail(project: ProjectModel, task: TaskModel):
        values = {
            "knowledge": task.knowledge_detail,
            "commerce": task.commerce_detail,
            "drama": task.drama_episode,
        }
        detail = values.get(project.mode)
        if detail is None or sum(value is not None for value in values.values()) != 1:
            raise ValidationException("Task Detail 必须且只能与 Project 模式匹配。")
        return detail

    @staticmethod
    def _columns(model) -> dict[str, Any] | None:
        if model is None:
            return None
        return {
            attribute.key: getattr(model, attribute.key)
            for attribute in inspect(model).mapper.column_attrs
            if attribute.key not in {"created_at", "updated_at"}
        }

    @staticmethod
    def _drama_reference_asset_ids(model) -> list[str]:
        values: list[str] = []
        for container_name in ("appearance_rules", "continuity_data"):
            container = getattr(model, container_name, None) or {}
            candidate = container.get("reference_asset_id")
            if isinstance(candidate, str) and candidate:
                values.append(candidate)
            values.extend(
                item for item in container.get("reference_asset_ids", [])
                if isinstance(item, str) and item
            )
        return values

    @staticmethod
    def _drama_shot_unit(shot: DramaTaskShotModel) -> dict[str, Any]:
        return {
            "id": shot.id,
            "visual_role": "concept",
            "production_metadata": {
                "drama_shot_id": shot.id,
                "duration_seconds": shot.duration_hint,
            },
        }
