"""Commerce-specific structural checks before a task can be published."""
from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.domain.commerce import DYNAMIC_FACT_TOKENS, is_dynamic_fact_field
from src.domain.enums import ProductionMode, VisualRole
from src.models.asset import AssetModel
from src.models.creative_plan import CreativePlanModel
from src.repositories.task_repository import TaskRepository
from src.schemas.creative_plan import (
    CommercePreflightFinding,
    CommercePreflightResponse,
    CreativePlanResponse,
)
from src.schemas.product import ProductTruthSheet
from src.services.product_service import ProductService

_PRODUCT_ROLES = {
    VisualRole.PRODUCT_SHOT.value,
    VisualRole.PROOF.value,
    VisualRole.CTA.value,
}
_DYNAMIC_TEXT_TOKENS = tuple(
    sorted(
        {
            *DYNAMIC_FACT_TOKENS,
            "sale price",
            "original price",
            "折",
            "%",
            "¥",
            "￥",
        },
        key=len,
        reverse=True,
    )
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _same_value(left: Any, right: Any) -> bool:
    return _text(left).casefold() == _text(right).casefold()


class CommercePreflightService:
    """Run the small, explainable Commerce gate without invoking providers."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tasks = TaskRepository(session)
        self.products = ProductService(session)

    @staticmethod
    def _finding(
        code: str,
        severity: str,
        message: str,
        scene_ids: list[str] | None = None,
    ) -> CommercePreflightFinding:
        return CommercePreflightFinding(
            code=code,
            severity=severity,
            message=message,
            scene_ids=scene_ids or [],
        )

    @staticmethod
    def _dynamic_text(task, plan: CreativePlanResponse | None) -> str:
        values: list[str] = [
            str((task.input_payload or {}).get("hook") or ""),
            str((task.input_payload or {}).get("narration") or ""),
        ]
        if plan:
            values.extend(
                [
                    plan.hook,
                    plan.core_message,
                    plan.cta,
                    *(claim.text for claim in plan.claims),
                    *(item.narration for item in plan.scene_outline),
                ]
            )
        values.extend(
            scene.narration_text
            for scene in getattr(task, "scenes", [])
        )
        return "\n".join(values).casefold()

    @staticmethod
    def _plan_snapshot(task, plan: CreativePlanModel | None) -> CreativePlanResponse | None:
        raw = (task.input_payload or {}).get("creative_plan_snapshot")
        if isinstance(raw, dict):
            try:
                return CreativePlanResponse.model_validate(raw)
            except Exception:
                pass
        return CreativePlanResponse.model_validate(plan) if plan else None

    async def run(
        self,
        task_id: str,
        *,
        require_media: bool = False,
    ) -> CommercePreflightResponse:
        task = await self.tasks.get_with_scenes(task_id)
        if not task:
            raise NotFoundException("Task", task_id)

        checked_at = datetime.now(UTC)
        findings: list[CommercePreflightFinding] = []
        if task.production_mode != ProductionMode.COMMERCE.value:
            findings.append(
                self._finding(
                    "not_commerce_task",
                    "warning",
                    "该任务不是 Commerce 生产模式，未应用 Commerce 专项检查。",
                )
            )
            return CommercePreflightResponse(
                task_id=task.id,
                status="warning",
                blocking=False,
                checked_at=checked_at,
                findings=findings,
                summary={"scene_count": len(task.scenes or []), "checked_media": require_media},
            )

        product = await self.products.get_product(task.product_id) if task.product_id else None
        truth = ProductTruthSheet.model_validate(product.truth_sheet or {}) if product else ProductTruthSheet()
        plan_model = (
            await self.session.get(CreativePlanModel, task.creative_plan_id)
            if task.creative_plan_id
            else None
        )
        plan = self._plan_snapshot(task, plan_model)
        scenes = list(task.scenes or [])
        product_assets = {
            item.id: item.asset_id
            for item in (product.assets if product else [])
            if item.asset_id
        }
        product_asset_ids = set(product_assets.values())

        if not product:
            findings.append(self._finding("product_missing", "error", "Commerce 任务没有可用商品。"))

        locked_product_scenes: list[Any] = []
        for scene in scenes:
            commerce = (scene.production_metadata or {}).get("commerce") or {}
            role = str(commerce.get("role") or scene.visual_role or "")
            locked = bool(commerce.get("asset_locked") or role in _PRODUCT_ROLES)
            if not locked:
                continue
            locked_product_scenes.append(scene)
            product_asset_row_id = (scene.layout_params or {}).get("commerce_product_asset_id")
            if product_asset_row_id and product_asset_row_id not in product_assets:
                findings.append(
                    self._finding(
                        "wrong_product_asset",
                        "error",
                        "商品锁定镜头引用了不属于当前商品的 Product Asset。",
                        [scene.id],
                    )
                )
            if not scene.media_asset_id:
                findings.append(
                    self._finding(
                        "product_asset_missing",
                        "error",
                        "商品锁定镜头没有绑定原始 Product Asset。",
                        [scene.id],
                    )
                )
            elif scene.media_asset_id not in product_asset_ids:
                findings.append(
                    self._finding(
                        "wrong_product_asset",
                        "error",
                        "商品镜头使用了当前商品资产之外的媒体。",
                        [scene.id],
                    )
                )

        product_display_severity = "error" if require_media else "warning"
        if not locked_product_scenes:
            findings.append(
                self._finding(
                    "product_not_shown",
                    product_display_severity,
                    "Storyboard 中没有可识别的商品展示镜头。",
                )
            )
        elif not product_assets:
            findings.append(
                self._finding(
                    "product_asset_missing",
                    "error",
                    "商品没有可复用的原始 Product Asset，不能安全发布。",
                )
            )

        truth_claims = {
            claim.id: claim
            for claim in [*truth.selling_points, *truth.numerical_claims]
        }
        referenced_claim_ids: set[str] = set()
        for scene in scenes:
            referenced_claim_ids.update(scene.claim_refs or [])
        if plan:
            referenced_claim_ids.update(claim.id for claim in plan.claims)
        for claim_id in sorted(referenced_claim_ids):
            claim = truth_claims.get(claim_id)
            plan_claim = next((item for item in (plan.claims if plan else []) if item.id == claim_id), None)
            evidence_refs = list(claim.evidence_refs if claim else (plan_claim.evidence_refs if plan_claim else []))
            if not claim and not plan_claim:
                findings.append(
                    self._finding(
                        "claim_without_source",
                        "error",
                        f"主张 {claim_id} 不存在于商品 Truth Sheet。",
                    )
                )
            elif not evidence_refs:
                findings.append(
                    self._finding(
                        "claim_without_source",
                        "error",
                        f"主张 {claim_id} 没有可追溯来源。",
                    )
                )

        if plan and not _text(plan.cta):
            findings.append(self._finding("cta_missing", "error", "Creative Plan 缺少 CTA。"))
        if scenes and not any(
            str((scene.production_metadata or {}).get("commerce", {}).get("role") or scene.visual_role)
            == VisualRole.CTA.value
            for scene in scenes
        ):
            findings.append(self._finding("cta_missing", "error", "Storyboard 中缺少 CTA 镜头。"))

        fact_snapshot = (plan.fact_snapshot if plan else None) or (task.input_payload or {}).get("fact_snapshot")
        fact_snapshot = fact_snapshot if isinstance(fact_snapshot, dict) else {}
        dynamic_text = self._dynamic_text(task, plan)
        dynamic_reference = any(token.casefold() in dynamic_text for token in _DYNAMIC_TEXT_TOKENS)
        dynamic_facts = fact_snapshot.get("dynamic_facts") or {}
        if dynamic_reference:
            if not fact_snapshot.get("captured_at") or not dynamic_facts:
                findings.append(
                    self._finding(
                        "dynamic_fact_snapshot_missing",
                        "error",
                        "价格、折扣或活动信息进入文案，但缺少明确的事实 snapshot 时间。",
                    )
                )
            elif not fact_snapshot.get("confirmed_by_user"):
                findings.append(
                    self._finding(
                        "dynamic_fact_unconfirmed",
                        "warning",
                        "文案包含动态价格、折扣或活动事实；当前使用带时间的 snapshot，但尚未记录用户确认。",
                    )
                )
            current_dynamic = {
                fact.field: fact.value
                for fact in truth.facts
                if is_dynamic_fact_field(fact.field)
            }
            if product and product.price:
                current_dynamic.setdefault("price", product.price)
            stale_fields = [
                field
                for field, snapshot in dynamic_facts.items()
                if field in current_dynamic
                and isinstance(snapshot, dict)
                and not _same_value(snapshot.get("value"), current_dynamic[field])
            ]
            if stale_fields:
                findings.append(
                    self._finding(
                        "dynamic_fact_stale",
                        "error",
                        f"动态事实 snapshot 已过期：{', '.join(stale_fields)}。请重新确认后再发布。",
                    )
                )

        scene_keys = [
            (
                re.sub(r"\s+", " ", _text(scene.narration_text)).casefold(),
                re.sub(r"\s+", " ", _text(scene.visual_prompt)).casefold(),
                str(scene.visual_role),
                tuple(sorted(scene.claim_refs or [])),
            )
            for scene in scenes
        ]
        duplicate_scene_ids: list[str] = []
        for key, count in Counter(scene_keys).items():
            if count > 1:
                duplicate_scene_ids.extend(
                    scene.id for scene, scene_key in zip(scenes, scene_keys) if scene_key == key
                )
        if duplicate_scene_ids:
            findings.append(
                self._finding(
                    "scene_duplicate",
                    "warning",
                    "Storyboard 中存在内容完全重复的 Scene，请确认是否为有意重复。",
                    duplicate_scene_ids,
                )
            )

        if not scenes:
            findings.append(
                self._finding(
                    "scene_missing",
                    "error" if require_media else "warning",
                    "任务还没有 storyboard Scene。",
                )
            )
        invalid_duration_ids = [
            scene.id for scene in scenes if float(scene.duration_seconds or 0) <= 0
        ]
        if invalid_duration_ids:
            findings.append(
                self._finding(
                    "duration_invalid",
                    "error",
                    "存在时长为 0 或负数的 Scene。",
                    invalid_duration_ids,
                )
            )
        total_duration = sum(max(float(scene.duration_seconds or 0), 0) for scene in scenes)
        if scenes and total_duration <= 0:
            findings.append(self._finding("duration_missing", "error", "Storyboard 总时长无效。"))

        missing_audio_ids = [scene.id for scene in scenes if not scene.audio_asset_id]
        missing_clip_ids = [scene.id for scene in scenes if not scene.rendered_segment_asset_id]
        media_severity = "error" if require_media else "warning"
        if missing_audio_ids:
            findings.append(
                self._finding(
                    "audio_missing",
                    media_severity,
                    "部分 Scene 尚未绑定配音素材。",
                    missing_audio_ids,
                )
            )
        if missing_clip_ids:
            findings.append(
                self._finding(
                    "scene_media_missing",
                    media_severity,
                    "部分 Scene 尚未生成可合成的媒体片段。",
                    missing_clip_ids,
                )
            )

        result_payload = task.result_payload or {}
        final_asset_id = result_payload.get("final_video_asset_id")
        subtitle_ids = result_payload.get("subtitle_artifact_ids")
        if require_media and not final_asset_id:
            findings.append(self._finding("final_video_missing", "error", "发布前没有可用的最终视频。"))
        if require_media and "subtitle_artifact_ids" in result_payload and not subtitle_ids:
            findings.append(self._finding("subtitles_missing", "warning", "最终结果未登记字幕 artifact。"))
        if final_asset_id:
            final_asset = await self.session.get(AssetModel, final_asset_id)
            if not final_asset:
                findings.append(self._finding("final_video_missing", "error", "最终视频 Asset 不存在。"))
            elif float(final_asset.duration_seconds or 0) <= 0:
                findings.append(self._finding("duration_invalid", "error", "最终视频时长无效。"))
            elif (final_asset.metadata_json or {}).get("has_audio") is False:
                findings.append(self._finding("audio_missing", "error", "最终视频没有音频流。"))

        has_error = any(item.severity == "error" for item in findings)
        has_warning = any(item.severity == "warning" for item in findings)
        status = "fail" if has_error else "warning" if has_warning else "pass"
        response = CommercePreflightResponse(
            task_id=task.id,
            status=status,
            blocking=has_error,
            checked_at=checked_at,
            findings=findings,
            summary={
                "product_id": task.product_id,
                "creative_plan_id": task.creative_plan_id,
                "scene_count": len(scenes),
                "total_duration_seconds": round(total_duration, 3),
                "checked_media": require_media,
                "dynamic_fact_snapshot_at": fact_snapshot.get("captured_at"),
            },
        )
        task.result_payload = {
            **(task.result_payload or {}),
            "commerce_preflight_qa": response.model_dump(mode="json"),
        }
        await self.session.commit()
        return response
