import pytest

from src.domain.enums import ProductionMode
from src.domain.production_recipes import (
    MediaStrategy,
    compile_production_plan,
    resolve_recipe,
)
from src.models.production_context import ProductionContextSnapshotModel
from src.models.scene import SceneModel
from src.models.workflow import WorkflowJobModel
from src.services.production_pipeline import production_pipeline_registry


def test_recipe_planners_keep_mode_and_per_scene_strategy_explicit():
    scenes = [
        {"id": "data", "visual_role": "data", "production_metadata": {}},
        {"id": "example", "visual_role": "example", "production_metadata": {}},
        {"id": "concept", "visual_role": "concept", "production_metadata": {}},
    ]
    plan = compile_production_plan(
        "knowledge", {"recipe_id": "knowledge_smart_mix"}, scenes
    )
    assert plan.mode == ProductionMode.KNOWLEDGE
    assert plan.scene_plans["data"].strategy == MediaStrategy.STATIC_CARD
    assert plan.scene_plans["example"].strategy == MediaStrategy.ONLINE_ASSET
    assert plan.scene_plans["concept"].strategy == MediaStrategy.TEXT_TO_IMAGE
    assert resolve_recipe("drama", "drama_reference_i2v").default_strategy == MediaStrategy.IMAGE_TO_VIDEO


def test_registry_uses_mode_specific_workflow_with_shared_executor():
    job = type("Job", (), {"params": {}})()
    for mode in ProductionMode:
        pipeline = production_pipeline_registry.create(mode, None, job)
        assert pipeline.production_mode == mode
        assert pipeline.workflow.mode == mode
        assert {"assets", "voice", "composition", "export"} <= set(
            pipeline.workflow.stage_keys
        )


@pytest.mark.asyncio
async def test_explicit_recipe_capability_failure_is_not_silently_downgraded(
    client, monkeypatch
):
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Knowledge", "mode": "knowledge", "knowledge_profile": {}},
        )
    ).json()["data"]
    task = (
        await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={
                "title": "Dynamic",
                "detail": {"type": "knowledge", "topic": "Dynamic"},
                "generation_settings": {"recipe_id": "knowledge_dynamic"},
            },
        )
    ).json()["data"]
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {"llm": {"id": "llm"}, "video": None}

    monkeypatch.setattr(
        "src.services.provider_manager.ProviderManager.capture_snapshot", providers
    )
    response = await client.post(f"/api/v1/tasks/{task['id']}/jobs")
    assert response.status_code == 422
    assert "video" in response.text
    assert "knowledge_dynamic" in (
        await client.get("/api/v1/tasks/recipes?mode=knowledge")
    ).text


@pytest.mark.asyncio
async def test_snapshot_freezes_mixed_media_plan_and_retry_reuses_it(
    client, test_session, monkeypatch
):
    project = (
        await client.post(
            "/api/v1/projects",
            json={"name": "Knowledge", "mode": "knowledge", "knowledge_profile": {}},
        )
    ).json()["data"]
    task = (
        await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={
                "title": "Mixed",
                "detail": {"type": "knowledge", "topic": "Mixed"},
                "generation_settings": {"recipe_id": "knowledge_smart_mix"},
            },
        )
    ).json()["data"]
    test_session.add_all(
        [
            SceneModel(
                id="scene_data",
                task_id=task["id"],
                sequence_index=0,
                visual_role="data",
            ),
            SceneModel(
                id="scene_example",
                task_id=task["id"],
                sequence_index=1,
                visual_role="example",
            ),
        ]
    )
    await test_session.commit()
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {
            "llm": {"id": "llm"},
            "image": {"id": "image"},
            "material": {"id": "material"},
        }

    monkeypatch.setattr(
        "src.services.provider_manager.ProviderManager.capture_snapshot", providers
    )
    job_data = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    job = await test_session.get(WorkflowJobModel, job_data["id"])
    snapshot = await test_session.get(
        ProductionContextSnapshotModel, job.production_context_snapshot_id
    )
    plans = snapshot.context_payload["production_plan"]["scene_plans"]
    assert plans["scene_data"]["strategy"] == "static_card"
    assert plans["scene_example"]["strategy"] == "online_asset"

    job.status = "failed"
    await test_session.commit()
    await client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"generation_settings": {"recipe_id": "knowledge_quick"}},
    )
    retry = (await client.post(f"/api/v1/workflow-jobs/{job.id}/retry")).json()["data"]
    retry_model = await test_session.get(WorkflowJobModel, retry["id"])
    assert retry_model.production_context_snapshot_id == snapshot.id
