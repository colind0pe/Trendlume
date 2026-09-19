from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.domain.enums import AssetType, CreativeAngle, ProductionMode, VisualRole
from src.models import ProjectModel, SceneModel, TaskModel
from src.schemas.product import ProductClaimInput, ProductCreate, ProductUpdate
from src.services.commerce_pipeline import CommerceProductionPipeline
from src.services.commerce_planning_service import CommercePlanningService
from src.services.commerce_preflight import CommercePreflightService
from src.services.product_service import ProductService
from src.storage.local_storage import LocalStorageService


@pytest.mark.asyncio
async def test_three_creative_plans_are_created_without_media_or_tasks(test_session):
    product = await ProductService(test_session).create_product(
        ProductCreate(
            title="低成本规划商品",
            brand="Demo",
            price="99",
            selling_points=[ProductClaimInput(text="用户确认卖点")],
        )
    )

    plans = await CommercePlanningService(test_session).generate_plans(product.id)

    assert len(plans) == 3
    assert {plan.status for plan in plans} == {"draft"}
    assert all(plan.hook and plan.audience and plan.core_message and plan.cta for plan in plans)
    assert all(plan.scene_outline and plan.fact_snapshot["captured_at"] for plan in plans)
    assert all(plan.claims[0]["evidence_refs"] for plan in plans)
    assert await test_session.scalar(select(TaskModel.id).where(TaskModel.product_id == product.id)) is None
    assert await test_session.scalar(select(SceneModel.id)) is None


@pytest.mark.asyncio
async def test_selected_plan_can_be_duplicated_and_translated_to_storyboard(test_session):
    product = await ProductService(test_session).create_product(
        ProductCreate(title="可复制 Variant 商品", brand="Demo")
    )
    planning = CommercePlanningService(test_session)
    plans = await planning.generate_plans(product.id)
    selected = await planning.select_plan(product.id, plans[1].id)
    variant = await planning.duplicate_plan(product.id, selected.id, "场景 Variant")

    assert selected.status == "selected"
    assert variant.status == "variant"
    assert variant.source_plan_id == selected.id
    assert variant.fact_snapshot == selected.fact_snapshot
    assert variant.scene_outline == selected.scene_outline

    script = CommerceProductionPipeline._script_from_plan(product=product, plan=selected)
    assert len(script.scenes) == len(selected.scene_outline)
    assert script.scenes[1].visual_role == VisualRole.PRODUCT_SHOT
    assert script.scenes[1].production_metadata["commerce"]["asset_locked"] is True
    assert script.scenes[1].production_metadata["commerce"]["deterministic_transform"] == (
        "crop_scale_ken_burns_overlay"
    )


@pytest.mark.asyncio
async def test_commerce_preflight_checks_product_claims_and_media_state(test_session, tmp_path):
    project = ProjectModel(id=f"project_{uuid4().hex[:8]}", name="Commerce QA")
    test_session.add(project)
    await test_session.flush()
    product_service = ProductService(
        test_session,
        storage=LocalStorageService(tmp_path / "storage"),
    )
    product = await product_service.create_product(
        ProductCreate(
            title="QA 商品",
            price="129",
            selling_points=[ProductClaimInput(text="可追溯卖点")],
        )
    )
    product_asset = await product_service.add_asset(
        product.id,
        content=b"product-image",
        file_name="hero.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
        role="hero",
    )
    assert product_asset.asset_id
    plan_service = CommercePlanningService(test_session)
    plan = (await plan_service.generate_plans(product.id))[0]
    plan = await plan_service.select_plan(product.id, plan.id)
    task = TaskModel(
        id=f"task_{uuid4().hex[:8]}",
        project_id=project.id,
        product_id=product.id,
        creative_plan_id=plan.id,
        production_mode=ProductionMode.COMMERCE.value,
        creative_angle=CreativeAngle(plan.angle).value,
        title="Commerce QA task",
        input_payload={
            "creative_plan_snapshot": await plan_service.plan_payload(plan.id),
        },
    )
    test_session.add(task)
    await test_session.flush()
    claim_id = plan.claims[0]["id"] if plan.claims else ""
    test_session.add_all(
        [
            SceneModel(
                id=f"scene_{uuid4().hex[:8]}",
                task_id=task.id,
                sequence_index=0,
                narration_text="先看清商品。",
                visual_prompt="使用商品原始资产，只做裁切缩放。",
                visual_role=VisualRole.PRODUCT_SHOT.value,
                duration_seconds=4,
                media_asset_id=product_asset.asset_id,
                layout_params={"commerce_product_asset_id": product_asset.id},
                production_metadata={"commerce": {"role": "product_shot", "asset_locked": True}},
            ),
            SceneModel(
                id=f"scene_{uuid4().hex[:8]}",
                task_id=task.id,
                sequence_index=1,
                narration_text="这是已确认的卖点。",
                visual_prompt="使用确定性排版表达事实。",
                visual_role=VisualRole.BENEFIT.value,
                claim_refs=[claim_id] if claim_id else [],
                duration_seconds=4,
                production_metadata={"commerce": {"role": "benefit", "asset_locked": False}},
            ),
            SceneModel(
                id=f"scene_{uuid4().hex[:8]}",
                task_id=task.id,
                sequence_index=2,
                narration_text=plan.cta,
                visual_prompt="商品资产加 CTA 排版。",
                visual_role=VisualRole.CTA.value,
                duration_seconds=4,
                media_asset_id=product_asset.asset_id,
                layout_params={"commerce_product_asset_id": product_asset.id},
                production_metadata={"commerce": {"role": "cta", "asset_locked": True}},
            ),
        ]
    )
    await test_session.commit()

    result = await CommercePreflightService(test_session).run(task.id)

    assert result.blocking is False
    assert result.status == "warning"  # media is intentionally not generated in this test
    assert not {finding.code for finding in result.findings} & {
        "product_not_shown",
        "wrong_product_asset",
        "claim_without_source",
        "cta_missing",
    }
    assert {finding.code for finding in result.findings} >= {"audio_missing", "scene_media_missing"}


@pytest.mark.asyncio
async def test_commerce_preflight_blocks_stale_dynamic_facts_and_wrong_storyboard(test_session, tmp_path):
    project = ProjectModel(id=f"project_{uuid4().hex[:8]}", name="Commerce QA failures")
    test_session.add(project)
    await test_session.flush()
    product_service = ProductService(
        test_session,
        storage=LocalStorageService(tmp_path / "storage"),
    )
    product = await product_service.create_product(ProductCreate(title="动态事实商品", price="99"))
    product_asset = await product_service.add_asset(
        product.id,
        content=b"product-image",
        file_name="hero.png",
        mime_type="image/png",
        asset_type=AssetType.IMAGE,
        role="hero",
    )
    assert product_asset.asset_id
    planning = CommercePlanningService(test_session)
    plan = await planning.select_plan(
        product.id,
        (await planning.generate_plans(product.id))[0].id,
    )
    await product_service.update_product(product.id, ProductUpdate(price="199"))
    task = TaskModel(
        id=f"task_{uuid4().hex[:8]}",
        project_id=project.id,
        product_id=product.id,
        creative_plan_id=plan.id,
        production_mode=ProductionMode.COMMERCE.value,
        creative_angle=plan.angle,
        title="失败 QA task",
        input_payload={"creative_plan_snapshot": await planning.plan_payload(plan.id)},
    )
    test_session.add(task)
    await test_session.flush()
    duplicate_scenes = [
        SceneModel(
            id=f"scene_{uuid4().hex[:8]}",
            task_id=task.id,
            sequence_index=index,
            narration_text="价格 199 元，限时 8 折。",
            visual_prompt="同一张事实卡。",
            visual_role=VisualRole.BENEFIT.value,
            claim_refs=["claim-does-not-exist"],
            duration_seconds=0,
            production_metadata={"commerce": {"role": "benefit"}},
        )
        for index in range(2)
    ]
    duplicate_scenes.append(
        SceneModel(
            id=f"scene_{uuid4().hex[:8]}",
            task_id=task.id,
            sequence_index=2,
            narration_text="展示错误素材。",
            visual_prompt="商品图",
            visual_role=VisualRole.PRODUCT_SHOT.value,
            duration_seconds=4,
            media_asset_id="asset-not-in-product",
            layout_params={"commerce_product_asset_id": "product-asset-not-in-product"},
            production_metadata={"commerce": {"role": "product_shot", "asset_locked": True}},
        )
    )
    test_session.add_all(duplicate_scenes)
    await test_session.commit()

    result = await CommercePreflightService(test_session).run(task.id, require_media=True)
    codes = {finding.code for finding in result.findings}

    assert result.blocking is True
    assert {"dynamic_fact_stale", "wrong_product_asset", "claim_without_source", "cta_missing", "scene_duplicate", "duration_invalid"} <= codes


@pytest.mark.asyncio
async def test_product_plan_api_selects_and_creates_task(client):
    product_response = await client.post(
        "/api/v1/products",
        json={"title": "规划 API 商品", "brand": "Demo", "selling_points": [{"text": "可追溯卖点"}]},
    )
    product_id = product_response.json()["data"]["id"]
    plans_response = await client.post(f"/api/v1/products/{product_id}/creative-plans", json={"count": 3})
    assert plans_response.status_code == 201
    plans = plans_response.json()["data"]
    assert len(plans) == 3

    selected_response = await client.post(
        f"/api/v1/products/{product_id}/creative-plans/{plans[0]['id']}/select"
    )
    assert selected_response.status_code == 200
    selected = selected_response.json()["data"]
    assert selected["status"] == "selected"

    project_response = await client.post(
        "/api/v1/projects",
        json={"name": "规划 API 项目", "primary_production_mode": "commerce"},
    )
    project_id = project_response.json()["data"]["id"]
    task_response = await client.post(
        f"/api/v1/products/{product_id}/creative-plans/{plans[0]['id']}/produce",
        json={"project_id": project_id},
    )
    assert task_response.status_code == 201
    assert task_response.json()["data"]["creative_plan_id"] == plans[0]["id"]
