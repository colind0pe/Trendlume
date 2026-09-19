"""Commerce-specific durable preparation layered on the shared media pipeline."""
from __future__ import annotations

from typing import Any

from src.core.exceptions import ValidationException
from src.domain.commerce import CREATIVE_ANGLE_LABELS
from src.domain.enums import CreativeAngle, ProductionMode, VisualRole
from src.domain.production_workflows import get_production_workflow
from src.models.creative_plan import CreativePlanModel
from src.models.product import ProductAssetModel
from src.repositories.scene_repository import SceneRepository
from src.repositories.task_repository import TaskRepository
from src.schemas.creative_plan import CreativePlanResponse, CreativeSceneOutline
from src.schemas.generation import (
    PlatformMetadata,
    StructuredSceneScript,
    StructuredScript,
)
from src.schemas.product import ProductTruthSheet
from src.services.durable_pipeline import DurableProductionPipeline, scene_snapshot
from src.services.product_service import ProductService


def _text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


class CommerceProductionPipeline(DurableProductionPipeline):
    """Build product facts and commercial editorial artifacts before shared media work."""

    production_mode = ProductionMode.COMMERCE
    workflow = get_production_workflow(ProductionMode.COMMERCE)
    preparation_stages = frozenset(
        {"product_ingest", "product_truth", "creative_strategy", "variant_selection", "script", "storyboard"}
    )

    async def prepare_mode_pipeline(
        self,
        task,
        project,
        payload,
        generator,
        provider_inputs,
        prompt_selection,
        single,
    ):
        requested = (
            self.params.get("force_step")
            or self.params.get("retry_step")
            or self.params.get("step_key")
        )
        if not payload.get("_commerce_prepared") or requested in self.preparation_stages:
            await self.prepare_commerce(
                task,
                project,
                payload,
                generator,
                provider_inputs,
                prompt_selection,
            )
            task = await TaskRepository(self.db).get_by_id(task.id)
            payload = dict(task.input_payload or {})
        if single in {"script", "research"}:
            single = None
        return payload, single, bool(payload.get("_commerce_prepared"))

    @staticmethod
    def _truth(product) -> ProductTruthSheet:
        try:
            truth = ProductTruthSheet.model_validate(product.truth_sheet or {})
        except Exception as exc:
            raise ValidationException("商品 Truth Sheet 无法校验，请先修正商品事实。") from exc
        if truth.product_id and truth.product_id != product.id:
            raise ValidationException("商品 Truth Sheet 与商品 ID 不一致。")
        truth.product_id = product.id
        return truth

    @staticmethod
    def _claims(truth: ProductTruthSheet) -> list[dict[str, Any]]:
        claims = [*truth.selling_points, *truth.numerical_claims]
        return [
            claim.model_dump(mode="json")
            for claim in claims
            if claim.evidence_refs and claim.certainty != "uncertain"
        ]

    @staticmethod
    def _evidence_refs(claims: list[dict[str, Any]]) -> list[str]:
        return list(dict.fromkeys(ref for claim in claims for ref in claim.get("evidence_refs", [])))[:20]

    def _scene_copy(
        self,
        *,
        role: VisualRole,
        product,
        truth: ProductTruthSheet,
        claims: list[dict[str, Any]],
        claim: dict[str, Any] | None,
        sequence_index: int,
    ) -> StructuredSceneScript:
        title = _text(product.title, 80)
        brand = _text(product.brand, 60)
        claim_text = _text((claim or {}).get("text"), 160)
        claim_refs = [str((claim or {}).get("id"))] if claim else []
        source_refs = list((claim or {}).get("evidence_refs") or [])
        product_identity = f"{brand} {title}".strip()
        if role in {VisualRole.PRODUCT_SHOT, VisualRole.PROOF, VisualRole.CTA}:
            narration = {
                VisualRole.PRODUCT_SHOT: f"先看清楚这件商品：{product_identity}。画面只使用商品库中的真实素材。",
                VisualRole.PROOF: (
                    f"关于{product_identity}，目前可以确认的是：{claim_text}。"
                    if claim_text
                    else "这一步只展示商品库中的真实素材，不补写未经确认的证明。"
                ),
                VisualRole.CTA: f"如果它符合你的需求，可以回到商品页核对信息，再决定是否了解{title}。",
            }[role]
            visual_prompt = (
                "商业商品镜头，直接使用商品库中的原始图片或视频素材；"
                "保持商品主体的颜色、形状、包装、文字和比例完全不变，不重绘、不改款、不添加未提供的配件；"
                "只做裁切、景别、光线和镜头运动处理，画面不出现额外可读文字、标志或水印。"
            )
        elif role == VisualRole.CONTEXT:
            narration = f"把它放回真实使用语境：先确认你要解决的场景，再看{title}是否适合。"
            visual_prompt = (
                "商业场景辅助镜头，展示干净、克制的使用环境和局部动作，商品主体不出镜或保持留白；"
                "不要凭空生成商品外观、品牌、功能和配件，不出现可读文字、标志或水印。"
            )
        elif role == VisualRole.BENEFIT:
            narration = f"真正值得关注的价值，是它能否对应你的实际需要。{claim_text}" if claim_text else "只表达已确认的商品信息，不把推测包装成承诺。"
            visual_prompt = (
                "商业利益点辅助镜头，使用抽象但可理解的动作、材质或空间关系表达使用感受；"
                "不生成商品主体，不添加未经商品事实支持的性能、效果、排名或绝对化结论。"
            )
        else:
            narration = f"把已确认的信息说清楚：{claim_text}" if claim_text else "商品资料仍有待确认，暂不作具体数值或效果承诺。"
            visual_prompt = (
                "商业说明辅助镜头，使用简洁的留白、局部手部动作或中性几何构图承载旁白；"
                "不生成商品主体，不出现未经核实的数字、对比结果、标志或可读文字。"
            )
        asset_locked = role in {VisualRole.PRODUCT_SHOT, VisualRole.PROOF, VisualRole.CTA}
        return StructuredSceneScript(
            sequence_index=sequence_index,
            narration_text=narration[:1000],
            visual_prompt=visual_prompt,
            badge_text={
                VisualRole.PRODUCT_SHOT: "商品实拍",
                VisualRole.CONTEXT: "使用场景",
                VisualRole.BENEFIT: "核心价值",
                VisualRole.PROOF: "事实依据",
                VisualRole.CTA: "了解更多",
            }.get(role, "商品信息"),
            visual_role=role,
            claim_refs=claim_refs,
            source_refs=source_refs,
            production_metadata={
                "commerce": {
                    "role": role.value,
                    "product_id": product.id,
                    "asset_locked": asset_locked,
                    "fact_refs": source_refs,
                    "claim_refs": claim_refs,
                },
                "media": {
                    "locked": asset_locked,
                    "source": "product" if asset_locked else "generated",
                },
            },
        )

    @staticmethod
    def _script_from_plan(
        *,
        product,
        plan: CreativePlanModel,
    ) -> StructuredScript:
        """Translate a reviewed plan into the shared storyboard contract.

        Plans contain editorial intent only.  This conversion keeps the media
        pipeline as the single place that turns that intent into scenes and
        explicitly records which scenes may reuse the original product asset.
        """
        plan_payload = CreativePlanResponse.model_validate(plan)
        claim_map = {claim.id: claim for claim in plan_payload.claims}
        outline = [
            CreativeSceneOutline.model_validate(item)
            for item in plan_payload.scene_outline
        ]
        if not outline:
            raise ValidationException("Creative Plan 缺少 scene outline，无法进入 storyboard。")

        scenes: list[StructuredSceneScript] = []
        for index, item in enumerate(outline):
            claim_refs = [ref for ref in item.claim_refs if ref in claim_map]
            source_refs = list(
                dict.fromkeys(
                    source_ref
                    for claim_ref in claim_refs
                    for source_ref in claim_map[claim_ref].evidence_refs
                )
            )
            role = item.visual_role
            asset_locked = item.asset_strategy == "product_asset" or role in {
                VisualRole.PRODUCT_SHOT,
                VisualRole.PROOF,
                VisualRole.CTA,
            }
            scenes.append(
                StructuredSceneScript(
                    sequence_index=index,
                    narration_text=item.narration,
                    visual_prompt=item.visual,
                    badge_text=item.beat,
                    visual_role=role,
                    claim_refs=claim_refs,
                    source_refs=source_refs,
                    production_metadata={
                        "commerce": {
                            "role": role.value,
                            "product_id": product.id,
                            "asset_locked": asset_locked,
                            "asset_strategy": item.asset_strategy,
                            "deterministic_transform": (
                                "crop_scale_ken_burns_overlay"
                                if asset_locked
                                else "deterministic_layout"
                            ),
                            "fact_refs": source_refs,
                            "claim_refs": claim_refs,
                        },
                        "media": {
                            "locked": asset_locked,
                            "source": "product" if asset_locked else "generated",
                        },
                    },
                )
            )

        product_title = _text(product.title, 80)
        return StructuredScript(
            title=_text(f"{product.brand} {product_title} · {plan.variant_label}", 80)
            or "商品介绍",
            hook=plan_payload.hook,
            narration=" ".join(scene.narration_text for scene in scenes),
            scenes=scenes,
            metadata=PlatformMetadata(
                title=_text(product_title, 30),
                description=_text(plan_payload.core_message, 1000),
                tags=[
                    "商品介绍",
                    CREATIVE_ANGLE_LABELS.get(
                        plan_payload.angle.value,
                        plan_payload.angle.value,
                    ),
                ],
                declaration="商品信息以商品库 Truth Sheet 为准",
            ),
        )

    async def prepare_commerce(
        self,
        task,
        project,
        payload: dict[str, Any],
        gen,
        provider_inputs: dict[str, Any],
        prompt_selection: dict[str, Any],
    ) -> None:
        del project
        product_id = task.product_id or payload.get("product_id")
        if not product_id:
            raise ValidationException("Commerce 生产任务缺少 product_id。")
        product = await ProductService(self.db, storage=self.storage).get_product(product_id)
        truth = self._truth(product)
        claims = self._claims(truth)
        evidence_refs = self._evidence_refs(claims)
        plan_id = task.creative_plan_id or payload.get("creative_plan_id")
        plan = None
        if plan_id:
            plan = await self.db.get(CreativePlanModel, str(plan_id))
            if not plan or plan.product_id != product.id:
                raise ValidationException("所选 Creative Plan 不属于当前商品。")
            if plan.status not in {"selected", "variant"}:
                raise ValidationException("请先选择 Creative Plan，再进入 storyboard/media 生产。")
        angle = str(task.creative_angle or payload.get("creative_angle") or CreativeAngle.DIRECT.value)
        if plan:
            angle = plan.angle
        try:
            angle = CreativeAngle(angle).value
        except ValueError as exc:
            raise ValidationException("Commerce 任务的创意角度无效。") from exc

        local_assets = [item for item in product.assets if item.asset_id]
        hero = next((item for item in local_assets if item.role == "hero"), None) or (local_assets[0] if local_assets else None)
        asset_rows = [
            {
                "id": item.id,
                "asset_id": item.asset_id,
                "asset_type": item.asset_type,
                "role": item.role,
                "source_kind": item.source_kind,
                "source_url": item.source_url,
            }
            for item in product.assets
        ]
        product_payload = {
            "product_id": product.id,
            "title": product.title,
            "brand": product.brand,
            "description": product.description,
            "price": product.price,
            "currency": product.currency,
            "specifications": product.specifications,
            "source_url": product.source_url,
            "source_snapshot": product.source_snapshot,
            "assets": asset_rows,
        }
        ingest_inputs = {
            "product_id": product.id,
            "source_url": product.source_url,
            "source_snapshot": product.source_snapshot,
            "assets": asset_rows,
        }
        _, ingest_artifacts = await self.json_stage(
            "product_ingest", ingest_inputs, product_payload
        )
        truth_payload = truth.model_dump(mode="json")
        _, truth_artifacts = await self.json_stage(
            "product_truth",
            {"product_id": product.id, "truth_sheet": truth_payload},
            truth_payload,
            dependencies=ingest_artifacts,
        )
        plan_snapshot = (
            CreativePlanResponse.model_validate(plan).model_dump(mode="json")
            if plan
            else None
        )
        if plan:
            strategy = {
                "product_id": product.id,
                "creative_plan_id": plan.id,
                "variant_label": plan.variant_label,
                "creative_angle": angle,
                "creative_angle_label": CREATIVE_ANGLE_LABELS[angle],
                "hook": plan.hook,
                "audience": plan.audience,
                "core_message": plan.core_message,
                "cta": plan.cta,
                "claim_ids": [claim["id"] for claim in plan.claims],
                "evidence_refs": evidence_refs,
                "unresolved_fields": truth.unresolved_fields,
                "truth_sheet_version": plan.truth_sheet_version,
                "fact_snapshot": plan.fact_snapshot,
                "locked_asset_id": hero.asset_id if hero else None,
                "locked_product_asset_id": hero.id if hero else None,
                "scene_outline_count": len(plan.scene_outline),
            }
        else:
            strategy = {
                "product_id": product.id,
                "creative_angle": angle,
                "creative_angle_label": CREATIVE_ANGLE_LABELS[angle],
                "hook": {
                    CreativeAngle.DIRECT.value: f"{product.title}，先把商品事实看清楚。",
                    CreativeAngle.PAIN_POINT.value: f"如果你正在为相关需求反复选择，先看清{product.title}。",
                    CreativeAngle.USE_CASE.value: f"在真实使用场景里，{product.title}是否适合你？",
                    CreativeAngle.DEMO.value: f"用真实素材看{product.title}能提供什么。",
                    CreativeAngle.REVIEW.value: f"不夸大，只把{product.title}已确认的信息讲明白。",
                    CreativeAngle.COMPARISON.value: f"选择{product.title}之前，先核对这些事实。",
                    CreativeAngle.STORY.value: f"从一个真实需求开始，认识{product.title}。",
                }[angle],
                "claim_ids": [claim["id"] for claim in claims],
                "evidence_refs": evidence_refs,
                "unresolved_fields": truth.unresolved_fields,
                "locked_asset_id": hero.asset_id if hero else None,
                "locked_product_asset_id": hero.id if hero else None,
                "scene_roles": [
                    VisualRole.PRODUCT_SHOT.value,
                    VisualRole.CONTEXT.value,
                    VisualRole.BENEFIT.value,
                    VisualRole.PROOF.value,
                    VisualRole.CTA.value,
                ],
            }
        _, strategy_artifacts = await self.json_stage(
            "creative_strategy",
            {
                "product_id": product.id,
                "angle": angle,
                "truth_version": truth.version,
                "claim_ids": strategy["claim_ids"],
                "provider_inputs": provider_inputs,
                "prompt_selection": prompt_selection,
            },
            strategy,
            dependencies=truth_artifacts,
        )

        variant_selection_payload = {
            "product_id": product.id,
            "creative_plan_id": plan.id if plan else None,
            "status": plan.status if plan else "unselected",
            "variant_label": plan.variant_label if plan else None,
            "source_plan_id": plan.source_plan_id if plan else None,
            "media_generation": "deferred_until_after_selection",
        }
        _, variant_selection_artifacts = await self.json_stage(
            "variant_selection",
            {
                "product_id": product.id,
                "creative_plan_id": plan.id if plan else None,
                "truth_sheet_version": truth.version,
            },
            variant_selection_payload,
            dependencies=strategy_artifacts,
        )

        if plan:
            script = self._script_from_plan(product=product, plan=plan)
            target_count = len(script.scenes)
        else:
            target_count = max(8, min(20, int(payload.get("target_scene_count") or 8)))
            claim_cycle = claims or [None]
            role_cycle = [
                VisualRole.PRODUCT_SHOT,
                VisualRole.CONTEXT,
                VisualRole.BENEFIT,
                VisualRole.PROOF,
                VisualRole.PRODUCT_SHOT,
                VisualRole.CONTEXT,
                VisualRole.BENEFIT,
                VisualRole.CTA,
            ]
            scenes = [
                self._scene_copy(
                    role=role_cycle[index % len(role_cycle)],
                    product=product,
                    truth=truth,
                    claims=claims,
                    claim=claim_cycle[index % len(claim_cycle)],
                    sequence_index=index,
                )
                for index in range(target_count)
            ]
            script = StructuredScript(
                title=_text(f"{product.brand} {product.title}".strip(), 80) or "商品介绍",
                hook=str(strategy["hook"]),
                narration=" ".join(scene.narration_text for scene in scenes),
                scenes=scenes,
                metadata=PlatformMetadata(
                    title=_text(product.title, 30),
                    description=_text(product.description or strategy["hook"], 1000),
                    tags=["商品介绍", CREATIVE_ANGLE_LABELS[angle]],
                    declaration="商品信息以商品库 Truth Sheet 为准",
                ),
            )
        script_payload = script.model_dump(mode="json", exclude_none=True)
        _, script_artifacts = await self.json_stage(
            "script",
            {
                "product_id": product.id,
                "creative_angle": angle,
                "target_scene_count": target_count,
                "strategy_claim_ids": strategy["claim_ids"],
                "creative_plan_id": plan.id if plan else None,
            },
            script_payload,
            dependencies=variant_selection_artifacts,
        )
        task_id = task.id
        script_data = StructuredScript.model_validate(script_payload)
        await self._apply_commerce_script(task_id, script_data, hero, gen)
        current = await SceneRepository(self.db).list_by_task_id(task_id)
        storyboard_payload = {
            "product_id": product.id,
            "creative_angle": angle,
            "scenes": [scene_snapshot(scene) for scene in current],
            "asset_policy": "product_shot/proof/cta 使用真实商品素材，缺失时失败而不重绘商品主体",
        }
        _, storyboard_artifacts = await self.json_stage(
            "storyboard",
            {"script_artifact_sha256": script_artifacts[0].sha256, "product_id": product.id},
            storyboard_payload,
            dependencies=script_artifacts,
        )
        del storyboard_artifacts
        fresh_task = await TaskRepository(self.db).get_by_id(task_id)
        fresh_task.input_payload = {
            **(fresh_task.input_payload or {}),
            "product_id": product.id,
            "creative_angle": angle,
            "creative_plan_id": plan.id if plan else None,
            "creative_plan_snapshot": plan_snapshot,
            "fact_snapshot": plan.fact_snapshot if plan else None,
            "commerce": {
                "product_id": product.id,
                "creative_plan_id": plan.id if plan else None,
                "variant_label": plan.variant_label if plan else None,
                "truth_sheet_version": truth.version,
                "creative_angle": angle,
                "locked_product_asset_id": hero.id if hero else None,
                "locked_asset_id": hero.asset_id if hero else None,
                "claim_ids": strategy["claim_ids"],
                "unresolved_fields": truth.unresolved_fields,
            },
            "_commerce_prepared": True,
        }
        await self.save()

    async def _apply_commerce_script(
        self,
        task_id: str,
        script: StructuredScript,
        hero: ProductAssetModel | None,
        generator,
    ) -> None:
        task = await TaskRepository(self.db).get_by_id(task_id)
        if not task:
            raise ValidationException("任务不存在，无法写入商业分镜。")
        # GenerationService remains the single scene replacement path and
        # keeps the active workflow execution context on the scene writes.
        await generator.apply_script_to_task(task_id, script)
        scenes = await SceneRepository(self.db).list_by_task_id(task_id)
        for scene in scenes:
            commerce = (scene.production_metadata or {}).get("commerce") or {}
            if not commerce.get("asset_locked"):
                continue
            if hero and hero.asset_id:
                scene.media_asset_id = hero.asset_id
                scene.layout_params = {
                    **(scene.layout_params or {}),
                    "media_source": "uploaded",
                    "commerce_product_asset_id": hero.id,
                    "commerce_asset_locked": True,
                    "commerce_asset_policy": "original_product_asset",
                    "commerce_transform": "crop_scale_ken_burns_overlay",
                }
                scene.production_metadata = {
                    **(scene.production_metadata or {}),
                    "media": {
                        "locked": True,
                        "asset_id": hero.asset_id,
                        "source": "product",
                    },
                }
            else:
                scene.layout_params = {
                    **(scene.layout_params or {}),
                    "commerce_asset_locked": True,
                    "commerce_product_asset_id": None,
                }
                scene.production_metadata = {
                    **(scene.production_metadata or {}),
                    "media": {"locked": True, "asset_id": None, "source": "product"},
                }
        await self.save()
