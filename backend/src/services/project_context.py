from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.enums import ProductionMode
from src.models.creative_plan import CreativePlanModel
from src.models.drama import DramaBibleModel, DramaEpisodeModel
from src.models.product import ProductModel
from src.models.project import ProjectModel
from src.models.project_context import (
    CommerceProjectProfileModel,
    KnowledgeContentItemModel,
    KnowledgeProjectProfileModel,
    ProjectContextVersionModel,
)
from src.schemas.project_context import (
    CommerceProfileInput,
    KnowledgeContentItemCreate,
    KnowledgeContentItemUpdate,
    KnowledgeProfileInput,
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def context_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _profile_payload(profile: Any) -> dict[str, Any] | None:
    if not profile:
        return None
    fields = (
        "positioning",
        "domain",
        "default_audience",
        "tone",
        "brand",
        "market",
        "audience",
        "marketing_goal",
        "brand_tone",
        "visual_system",
        "default_cta",
        "compliance_limits",
        "platform_defaults",
        "evidence_strategy",
    )
    return {
        field: getattr(profile, field)
        for field in fields
        if hasattr(profile, field)
    }


async def build_project_context(
    session: AsyncSession,
    project_id: str,
    *,
    knowledge_item_id: str | None = None,
    product_id: str | None = None,
    creative_plan_id: str | None = None,
    drama_episode_id: str | None = None,
) -> dict[str, Any]:
    project = await session.get(ProjectModel, project_id)
    if not project:
        raise NotFoundException("Project", project_id)

    mode = project.primary_production_mode or ProductionMode.KNOWLEDGE.value
    profile_model = {
        ProductionMode.KNOWLEDGE.value: KnowledgeProjectProfileModel,
        ProductionMode.COMMERCE.value: CommerceProjectProfileModel,
    }.get(mode)
    profile = await session.get(profile_model, project_id) if profile_model else None
    profile_payload = _profile_payload(profile)
    payload: dict[str, Any] = {
        "schema_version": 2,
        "production_mode": mode,
        "project": {
            "name": project.name,
            "description": project.description or "",
            "aspect_ratio": project.aspect_ratio,
            "default_voice_id": project.default_voice_id,
            "bgm_asset_id": project.bgm_asset_id,
            "settings": project.settings or {},
        },
        "profile": profile_payload,
    }
    if mode == ProductionMode.KNOWLEDGE.value:
        item = (
            await session.get(KnowledgeContentItemModel, knowledge_item_id)
            if knowledge_item_id
            else None
        )
        if knowledge_item_id and (not item or item.project_id != project_id):
            raise ValidationException("Knowledge 内容条目不存在或不属于当前项目。")
        payload["content_item"] = (
            {
                "id": item.id,
                "topic": item.topic,
                "audience": item.audience,
                "thesis": item.thesis,
                "takeaway": item.takeaway,
                "genre": item.genre,
                "key_claims": item.key_claims or [],
                "source_refs": item.source_refs or [],
                "review_status": item.review_status,
                "revision": item.revision,
            }
            if item
            else None
        )
    elif mode == ProductionMode.COMMERCE.value:
        product = await session.get(ProductModel, product_id) if product_id else None
        plan = await session.get(CreativePlanModel, creative_plan_id) if creative_plan_id else None
        if product_id and not product:
            raise ValidationException("Commerce 商品不存在。")
        if creative_plan_id and (not plan or (product and plan.product_id != product.id)):
            raise ValidationException("Commerce Creative Plan 与商品不匹配。")
        payload["product"] = (
            {
                "id": product.id,
                "title": product.title,
                "brand": product.brand,
                "description": product.description,
                "price": product.price,
                "currency": product.currency,
                "truth_sheet": product.truth_sheet or {},
                "source_snapshot": product.source_snapshot or {},
                "revision": getattr(product, "revision", 1),
            }
            if product
            else None
        )
        payload["creative_plan"] = (
            {
                "id": plan.id,
                "product_id": plan.product_id,
                "angle": plan.angle,
                "brief": {
                    "hook": plan.hook,
                    "audience": plan.audience,
                    "core_message": plan.core_message,
                    "claims": plan.claims or [],
                    "scene_outline": plan.scene_outline or [],
                    "cta": plan.cta,
                },
                "fact_snapshot": plan.fact_snapshot or {},
                "revision": getattr(plan, "revision", 1),
            }
            if plan
            else None
        )
    elif mode == ProductionMode.DRAMA.value:
        episode = await session.scalar(
            select(DramaEpisodeModel)
            .join(DramaBibleModel, DramaEpisodeModel.bible_id == DramaBibleModel.id)
            .where(
                DramaEpisodeModel.id == drama_episode_id,
                DramaBibleModel.project_id == project_id,
            )
        ) if drama_episode_id else None
        if drama_episode_id and not episode:
            raise ValidationException("Drama Episode 不存在或不属于当前项目。")
        bible = await session.scalar(
            select(DramaBibleModel)
            .where(DramaBibleModel.project_id == project_id)
            .options(
                selectinload(DramaBibleModel.characters),
                selectinload(DramaBibleModel.locations),
            )
        )
        payload["drama_bible"] = None
        if bible:
            payload["drama_bible"] = {
                "id": bible.id,
                "title": bible.title,
                "logline": bible.logline,
                "genre": bible.genre,
                "tone": bible.tone,
                "visual_style": bible.visual_style,
                "characters": [
                    {
                        "id": character.id,
                        "name": character.name,
                        "description": character.description,
                        "appearance_lock": character.appearance_lock,
                        "wardrobe": character.wardrobe,
                        "voice_id": character.voice_id,
                        "reference_asset_id": character.reference_asset_id,
                        "prompt_anchor": character.prompt_anchor,
                        "continuity_metadata": character.continuity_metadata or {},
                        "approval_status": character.approval_status,
                    }
                    for character in bible.characters
                ],
                "locations": [
                    {
                        "id": location.id,
                        "name": location.name,
                        "visual_description": location.visual_description,
                        "reference_asset_ids": location.reference_asset_ids or [],
                        "prompt_anchor": location.prompt_anchor,
                        "continuity_metadata": location.continuity_metadata or {},
                        "approval_status": location.approval_status,
                    }
                    for location in bible.locations
                ],
                "prop_locks": bible.prop_locks or [],
                "continuity_rules": bible.continuity_rules or [],
                "approval_status": bible.approval_status,
                "revision": bible.revision,
            }
        payload["episode"] = (
            {
                "id": episode.id,
                "episode_number": episode.episode_number,
                "title": episode.title,
                "synopsis": episode.synopsis,
                "script_text": episode.script_text,
                    "approval_status": episode.approval_status,
                "revision": getattr(episode, "revision", 1),
            }
            if episode
            else None
        )
    return payload


async def create_context_version(
    session: AsyncSession,
    project_id: str,
    *,
    knowledge_item_id: str | None = None,
    product_id: str | None = None,
    creative_plan_id: str | None = None,
    drama_episode_id: str | None = None,
) -> ProjectContextVersionModel:
    payload = await build_project_context(
        session,
        project_id,
        knowledge_item_id=knowledge_item_id,
        product_id=product_id,
        creative_plan_id=creative_plan_id,
        drama_episode_id=drama_episode_id,
    )
    digest = context_hash(payload)
    existing = await session.scalar(
        select(ProjectContextVersionModel).where(
            ProjectContextVersionModel.project_id == project_id,
            ProjectContextVersionModel.context_hash == digest,
        )
    )
    if existing:
        return existing
    latest = await session.scalar(
        select(ProjectContextVersionModel)
        .where(ProjectContextVersionModel.project_id == project_id)
        .order_by(ProjectContextVersionModel.version.desc())
        .limit(1)
    )
    version = ProjectContextVersionModel(
        id=f"ctx_{uuid4().hex[:12]}",
        project_id=project_id,
        version=(latest.version + 1) if latest else 1,
        context_hash=digest,
        context_payload=payload,
    )
    session.add(version)
    await session.flush()
    return version


async def assert_project_mode(
    session: AsyncSession, project_id: str, expected: ProductionMode
) -> ProjectModel:
    project = await session.get(ProjectModel, project_id)
    if not project:
        raise NotFoundException("Project", project_id)
    actual = project.primary_production_mode or ProductionMode.KNOWLEDGE.value
    if actual != expected.value:
        raise ValidationException(
            f"项目是 {actual} 模式，不能写入 {expected.value} 模式资源。"
        )
    return project


async def ensure_knowledge_profile(
    session: AsyncSession, project_id: str
) -> KnowledgeProjectProfileModel:
    await assert_project_mode(session, project_id, ProductionMode.KNOWLEDGE)
    profile = await session.get(KnowledgeProjectProfileModel, project_id)
    if profile:
        return profile
    profile = KnowledgeProjectProfileModel(project_id=project_id)
    session.add(profile)
    await session.flush()
    return profile


async def ensure_commerce_profile(
    session: AsyncSession, project_id: str
) -> CommerceProjectProfileModel:
    await assert_project_mode(session, project_id, ProductionMode.COMMERCE)
    profile = await session.get(CommerceProjectProfileModel, project_id)
    if profile:
        return profile
    profile = CommerceProjectProfileModel(project_id=project_id)
    session.add(profile)
    await session.flush()
    return profile


async def get_knowledge_profile(
    session: AsyncSession, project_id: str
) -> KnowledgeProjectProfileModel:
    return await ensure_knowledge_profile(session, project_id)


async def update_knowledge_profile(
    session: AsyncSession, project_id: str, data: KnowledgeProfileInput
) -> KnowledgeProjectProfileModel:
    profile = await ensure_knowledge_profile(session, project_id)
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    profile.revision += 1
    await session.flush()
    await session.commit()
    return profile


async def get_commerce_profile(
    session: AsyncSession, project_id: str
) -> CommerceProjectProfileModel:
    return await ensure_commerce_profile(session, project_id)


async def update_commerce_profile(
    session: AsyncSession, project_id: str, data: CommerceProfileInput
) -> CommerceProjectProfileModel:
    profile = await ensure_commerce_profile(session, project_id)
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    profile.revision += 1
    await session.flush()
    await session.commit()
    return profile


async def list_context_versions(
    session: AsyncSession, project_id: str
) -> list[ProjectContextVersionModel]:
    await _require_project(session, project_id)
    return list(
        (
            await session.scalars(
                select(ProjectContextVersionModel)
                .where(ProjectContextVersionModel.project_id == project_id)
                .order_by(ProjectContextVersionModel.version.desc())
            )
        ).all()
    )


async def list_knowledge_items(
    session: AsyncSession, project_id: str
) -> list[KnowledgeContentItemModel]:
    await assert_project_mode(session, project_id, ProductionMode.KNOWLEDGE)
    return list(
        (
            await session.scalars(
                select(KnowledgeContentItemModel)
                .where(KnowledgeContentItemModel.project_id == project_id)
                .order_by(KnowledgeContentItemModel.updated_at.desc())
            )
        ).all()
    )


async def create_knowledge_item(
    session: AsyncSession, project_id: str, data: KnowledgeContentItemCreate
) -> KnowledgeContentItemModel:
    await ensure_knowledge_profile(session, project_id)
    item = KnowledgeContentItemModel(project_id=project_id, **data.model_dump())
    session.add(item)
    await session.flush()
    await session.commit()
    return item


async def update_knowledge_item(
    session: AsyncSession, project_id: str, item_id: str, data: KnowledgeContentItemUpdate
) -> KnowledgeContentItemModel:
    await ensure_knowledge_profile(session, project_id)
    item = await session.get(KnowledgeContentItemModel, item_id)
    if not item or item.project_id != project_id:
        raise NotFoundException("KnowledgeContentItem", item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.revision += 1
    await session.flush()
    await session.commit()
    return item


async def _require_project(session: AsyncSession, project_id: str) -> ProjectModel:
    project = await session.get(ProjectModel, project_id)
    if not project:
        raise NotFoundException("Project", project_id)
    return project
