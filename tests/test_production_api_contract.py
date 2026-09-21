import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.api.app import create_app
from src.models.asset import AssetModel
from src.models.drama import DramaCharacterModel, DramaLocationModel, DramaPropModel
from src.models.project import ProjectAssetBindingModel
from src.models.publishing import SocialAccountModel
from src.models.workflow import WorkflowArtifactModel, WorkflowJobModel, WorkflowStepRunModel
from src.services.workflow_runtime import ArtifactSpec, WorkflowRuntime


def test_frontend_core_paths_are_registered_and_legacy_paths_are_absent():
    routes = set()
    for included in create_app().routes:
        router = getattr(included, "original_router", None)
        if router is None:
            continue
        prefix = included.include_context.prefix
        routes.update(
            (method, f"{prefix}{route.path}")
            for route in router.routes
            for method in getattr(route, "methods", set())
        )
    required = {
        ("GET", "/api/v1/tasks"),
        ("GET", "/api/v1/tasks/{task_id}"),
        ("PATCH", "/api/v1/tasks/{task_id}"),
        ("DELETE", "/api/v1/tasks/{task_id}"),
        ("POST", "/api/v1/tasks/{task_id}/approve"),
        ("GET", "/api/v1/tasks/{task_id}/readiness"),
        ("POST", "/api/v1/tasks/{task_id}/jobs"),
        ("GET", "/api/v1/tasks/{task_id}/jobs"),
        ("GET", "/api/v1/workflow-jobs/{job_id}"),
        ("POST", "/api/v1/workflow-jobs/{job_id}/retry"),
        ("POST", "/api/v1/workflow-jobs/{job_id}/cancel"),
        ("GET", "/api/v1/artifacts/{artifact_id}/download"),
        ("POST", "/api/v1/publishing/jobs"),
    }
    assert required <= routes

    api_client = (Path(__file__).parents[1] / "frontend/src/lib/api-client.ts").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "/tasks/${taskId}/generate",
        "/tasks/${taskId}/retry",
        "/tasks/${taskId}/resume",
        "/tasks/${taskId}/workflow",
        "/tasks/${taskId}/compose",
        "/tasks/${taskId}/publish",
        "/tasks/${taskId}/schedule",
        "/commerce-preflight",
    )
    assert not any(path in api_client for path in forbidden)
    registered_paths = {path for _, path in routes}
    static_client_paths = {
        "/api/v1" + value.split("?", 1)[0]
        for value in re.findall(r'["`](/[^"`$]*)["`]', api_client)
        if value != "/api/v1"
    }
    assert static_client_paths <= registered_paths
    task_dialog = (
        Path(__file__).parents[1]
        / "frontend/src/components/projects/production-task-dialog.tsx"
    ).read_text(encoding="utf-8")
    publishing_service = (
        Path(__file__).parents[1] / "backend/src/services/publishing_service.py"
    ).read_text(encoding="utf-8")
    assert "scheduled_publish" not in task_dialog
    assert "prepare_task_publishing" not in publishing_service


@pytest.mark.asyncio
async def test_job_history_and_detail_include_stages_and_artifacts(
    client, test_session, monkeypatch
):
    project = (await client.post("/api/v1/projects", json={
        "name": "Knowledge", "mode": "knowledge", "knowledge_profile": {"domain": "science"},
    })).json()["data"]
    task = (await client.post(f"/api/v1/projects/{project['id']}/tasks", json={
        "title": "Task", "detail": {"type": "knowledge", "topic": "Topic"},
    })).json()["data"]
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {"llm": {"provider_id": "test"}}

    monkeypatch.setattr(
        "src.services.provider_manager.ProviderManager.capture_snapshot", providers
    )
    job = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    run = WorkflowStepRunModel(
        id="run_contract",
        task_id=task["id"],
        job_id=job["id"],
        step_key="composition",
        unit_key="",
        attempt=1,
        input_fingerprint="0" * 64,
        input_payload={},
        status="completed",
        validity="valid",
        started_at=datetime.now(UTC),
    )
    artifact = WorkflowArtifactModel(
        id="artifact_contract",
        job_id=job["id"],
        task_id=task["id"],
        step_run_id=run.id,
        kind="final_video",
        relative_path="workflow/test/final.mp4",
        size_bytes=10,
        sha256="1" * 64,
        source="generated",
    )
    test_session.add_all([run, artifact])
    await test_session.commit()

    history = (await client.get(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    assert [item["id"] for item in history] == [job["id"]]
    global_tasks = (await client.get("/api/v1/tasks")).json()["data"]
    assert global_tasks[0]["latest_job"]["id"] == job["id"]
    project_tasks = (
        await client.get(f"/api/v1/projects/{project['id']}/tasks")
    ).json()["data"]
    assert project_tasks[0]["latest_job"]["id"] == job["id"]
    detail = (await client.get(f"/api/v1/workflow-jobs/{job['id']}")).json()["data"]
    assert detail["stages"][0]["step_key"] == "composition"
    assert detail["artifacts"][0]["kind"] == "final_video"
    assert detail["stages"][0]["artifacts"][0]["id"] == artifact.id


@pytest.mark.asyncio
async def test_artifact_download_rejects_wrong_job(client, test_session):
    artifact = await test_session.get(WorkflowArtifactModel, "missing")
    assert artifact is None
    response = await client.get(
        "/api/v1/artifacts/missing/download", params={"job_id": "wrong"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_project_assets_cannot_cross_project_boundary(client, test_session):
    project_a = (await client.post("/api/v1/projects", json={
        "name": "A", "mode": "knowledge", "knowledge_profile": {},
    })).json()["data"]
    project_b = (await client.post("/api/v1/projects", json={
        "name": "B", "mode": "commerce", "commerce_profile": {},
    })).json()["data"]
    asset = AssetModel(id="asset_a", asset_type="image", file_name="a.png", file_path="assets/a.png", mime_type="image/png")
    test_session.add_all([asset, ProjectAssetBindingModel(
        id="binding_a", project_id=project_a["id"], asset_id=asset.id, purpose="upload", metadata_json={},
    )])
    await test_session.commit()
    bind = await client.post(f"/api/v1/projects/{project_b['id']}/assets", json={"asset_id": asset.id, "purpose": "reference"})
    assert bind.status_code == 422
    await client.put(f"/api/v1/projects/{project_b['id']}/product", json={"title": "Product"})
    product_asset = await client.post(f"/api/v1/projects/{project_b['id']}/product/assets", json={"asset_id": asset.id})
    assert product_asset.status_code == 422


@pytest.mark.asyncio
async def test_unified_readiness_blocks_incomplete_modes(client):
    knowledge = (await client.post("/api/v1/projects", json={
        "name": "K", "mode": "knowledge", "knowledge_profile": {},
    })).json()["data"]
    knowledge_task = (await client.post(f"/api/v1/projects/{knowledge['id']}/tasks", json={
        "title": "K", "detail": {"type": "knowledge", "topic": "Topic"},
    })).json()["data"]
    pending = (await client.get(f"/api/v1/tasks/{knowledge_task['id']}/readiness")).json()["data"]
    assert pending["ready"] is False
    await client.post(f"/api/v1/tasks/{knowledge_task['id']}/approve")
    ready = (await client.get(f"/api/v1/tasks/{knowledge_task['id']}/readiness")).json()["data"]
    assert ready["ready"] is True

    commerce = (await client.post("/api/v1/projects", json={
        "name": "C", "mode": "commerce", "commerce_profile": {},
    })).json()["data"]
    commerce_task = (await client.post(f"/api/v1/projects/{commerce['id']}/tasks", json={
        "title": "C", "detail": {"type": "commerce", "creative_angle": "demo"},
    })).json()["data"]
    await client.post(f"/api/v1/tasks/{commerce_task['id']}/approve")
    commerce_ready = (await client.get(f"/api/v1/tasks/{commerce_task['id']}/readiness")).json()["data"]
    assert commerce_ready["ready"] is False
    assert {item["key"] for item in commerce_ready["checks"] if item["status"] == "error"} == {"commerce_product", "commerce_assets"}

    drama = (await client.post("/api/v1/projects", json={
        "name": "D", "mode": "drama",
        "drama_profile": {"series_title": "Series"}, "drama_style_guide": {},
    })).json()["data"]
    drama_task = (await client.post(f"/api/v1/projects/{drama['id']}/tasks", json={
        "title": "D", "detail": {"type": "drama", "episode_number": 1},
    })).json()["data"]
    await client.post(f"/api/v1/tasks/{drama_task['id']}/approve")
    drama_ready = (await client.get(f"/api/v1/tasks/{drama_task['id']}/readiness")).json()["data"]
    assert drama_ready["ready"] is False
    assert {"drama_characters", "drama_locations", "drama_props"} <= {item["key"] for item in drama_ready["checks"] if item["status"] == "error"}


@pytest.mark.asyncio
async def test_publishing_requires_successful_job_final_video_and_schedules_it(
    client, test_session, monkeypatch
):
    project = (await client.post("/api/v1/projects", json={
        "name": "Publish", "mode": "knowledge", "knowledge_profile": {},
    })).json()["data"]
    other_project = (await client.post("/api/v1/projects", json={
        "name": "Other", "mode": "knowledge", "knowledge_profile": {},
    })).json()["data"]
    task = (await client.post(f"/api/v1/projects/{project['id']}/tasks", json={
        "title": "Ready", "detail": {"type": "knowledge", "topic": "Ready"},
    })).json()["data"]
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {"llm": {"provider_id": "test"}}

    monkeypatch.setattr(
        "src.services.provider_manager.ProviderManager.capture_snapshot", providers
    )
    workflow = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    workflow_model = await test_session.get(WorkflowJobModel, workflow["id"])
    workflow_model.status = "completed"
    asset = AssetModel(
        id="publish_video",
        asset_type="video",
        file_name="final.mp4",
        file_path="tests/final.mp4",
        mime_type="video/mp4",
    )
    run = WorkflowStepRunModel(
        id="run_publish",
        task_id=task["id"],
        job_id=workflow["id"],
        step_key="composition",
        unit_key="",
        attempt=1,
        input_fingerprint="2" * 64,
        input_payload={},
        status="completed",
        validity="valid",
    )
    artifact = WorkflowArtifactModel(
        id="artifact_publish",
        job_id=workflow["id"],
        task_id=task["id"],
        step_run_id=run.id,
        asset_id=asset.id,
        kind="final_video",
        relative_path=asset.file_path,
        size_bytes=10,
        sha256="3" * 64,
        source="generated",
    )
    account = SocialAccountModel(
        id="account_publish",
        platform="douyin",
        account_name="Publisher",
        status="active",
    )
    test_session.add_all([asset, run, artifact, account])
    await test_session.commit()

    async def validated_asset(self, asset_id, *args, **kwargs):
        return await test_session.get(AssetModel, asset_id)

    monkeypatch.setattr(
        "src.services.publishing_service.PublishingService._validate_publish_asset",
        validated_asset,
    )
    payload = {
        "project_id": other_project["id"],
        "workflow_job_id": workflow["id"],
        "artifact_id": artifact.id,
        "account_id": account.id,
        "platform": "douyin",
        "title": "Publish",
    }
    assert (await client.post("/api/v1/publishing/jobs", json=payload)).status_code == 422

    submit = AsyncMock()
    monkeypatch.setattr("src.api.routes.publishing.task_manager.submit_task", submit)
    payload["project_id"] = project["id"]
    payload["scheduled_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    response = await client.post("/api/v1/publishing/jobs", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "scheduled"
    submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_artifacts_enforce_project_asset_ownership(
    client, test_session, monkeypatch, tmp_path
):
    project = (await client.post("/api/v1/projects", json={
        "name": "Owner", "mode": "knowledge", "knowledge_profile": {},
    })).json()["data"]
    other = (await client.post("/api/v1/projects", json={
        "name": "Other", "mode": "knowledge", "knowledge_profile": {},
    })).json()["data"]
    task = (await client.post(f"/api/v1/projects/{project['id']}/tasks", json={
        "title": "Owner task", "detail": {"type": "knowledge", "topic": "Owner"},
    })).json()["data"]
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {"llm": {"provider_id": "test"}}

    monkeypatch.setattr(
        "src.services.provider_manager.ProviderManager.capture_snapshot", providers
    )
    job_data = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    job = await test_session.get(WorkflowJobModel, job_data["id"])
    job.status = "running"
    job.lease_token = "lease_contract"

    foreign_asset = AssetModel(
        id="foreign_runtime_asset",
        asset_type="image",
        file_name="foreign.json",
        file_path="foreign.json",
        mime_type="application/json",
    )
    foreign_binding = ProjectAssetBindingModel(
        id="foreign_runtime_binding",
        project_id=other["id"],
        asset_id=foreign_asset.id,
        purpose="reference",
        metadata_json={},
    )
    run = WorkflowStepRunModel(
        id="foreign_runtime_run",
        task_id=task["id"],
        job_id=job.id,
        step_key="script",
        unit_key="",
        attempt=1,
        input_fingerprint="4" * 64,
        input_payload={},
        status="running",
        validity="valid",
    )
    test_session.add_all([foreign_asset, foreign_binding, run])
    await test_session.commit()
    output = tmp_path / "foreign.json"
    output.write_text("{}", encoding="utf-8")
    runtime = WorkflowRuntime(test_session, tmp_path, job.id, "lease_contract")
    with pytest.raises(ValueError, match="does not belong"):
        await runtime.complete(
            run,
            [ArtifactSpec(path=output, kind="script", asset_id=foreign_asset.id)],
        )


@pytest.mark.asyncio
async def test_all_modes_reach_approved_job_and_artifact(
    client, test_session, monkeypatch
):
    async def providers(self, **kwargs):
        return {"llm": {"provider_id": "test"}}

    monkeypatch.setattr(
        "src.services.provider_manager.ProviderManager.capture_snapshot", providers
    )
    cases = (
        (
            "knowledge",
            {"name": "Knowledge", "mode": "knowledge", "knowledge_profile": {}},
            {"type": "knowledge", "topic": "Topic"},
        ),
        (
            "commerce",
            {"name": "Commerce", "mode": "commerce", "commerce_profile": {}},
            {"type": "commerce", "creative_angle": "direct"},
        ),
        (
            "drama",
            {
                "name": "Drama",
                "mode": "drama",
                "drama_profile": {"series_title": "Series"},
                "drama_style_guide": {},
            },
            {"type": "drama", "episode_number": 1},
        ),
    )
    for index, (mode, project_payload, detail) in enumerate(cases):
        project = (await client.post("/api/v1/projects", json=project_payload)).json()["data"]
        if mode == "commerce":
            asset = AssetModel(
                id="commerce_closure_asset",
                asset_type="image",
                file_name="product.png",
                file_path="product.png",
                mime_type="image/png",
            )
            binding = ProjectAssetBindingModel(
                id="commerce_closure_binding",
                project_id=project["id"],
                asset_id=asset.id,
                purpose="product",
                metadata_json={},
            )
            test_session.add_all([asset, binding])
            await test_session.commit()
            await client.put(
                f"/api/v1/projects/{project['id']}/product",
                json={"title": "Product"},
            )
            await client.post(
                f"/api/v1/projects/{project['id']}/product/assets",
                json={"asset_id": asset.id},
            )
        elif mode == "drama":
            test_session.add_all(
                [
                    DramaCharacterModel(
                        id="closure_character",
                        project_id=project["id"],
                        name="Character",
                        approval_status="approved",
                    ),
                    DramaLocationModel(
                        id="closure_location",
                        project_id=project["id"],
                        name="Location",
                        approval_status="approved",
                    ),
                    DramaPropModel(
                        id="closure_prop",
                        project_id=project["id"],
                        name="Prop",
                        approval_status="approved",
                    ),
                ]
            )
            await test_session.commit()

        task = (await client.post(f"/api/v1/projects/{project['id']}/tasks", json={
            "title": f"{mode} task", "detail": detail,
        })).json()["data"]
        await client.post(f"/api/v1/tasks/{task['id']}/approve")
        job = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
        run = WorkflowStepRunModel(
            id=f"closure_run_{mode}",
            task_id=task["id"],
            job_id=job["id"],
            step_key="composition",
            unit_key="",
            attempt=1,
            input_fingerprint=str(index + 5) * 64,
            input_payload={},
            status="completed",
            validity="valid",
        )
        artifact = WorkflowArtifactModel(
            id=f"closure_artifact_{mode}",
            job_id=job["id"],
            task_id=task["id"],
            step_run_id=run.id,
            kind="final_video",
            relative_path=f"workflow/{mode}/final.mp4",
            size_bytes=10,
            sha256=str(index + 5) * 64,
            source="generated",
        )
        test_session.add_all([run, artifact])
        await test_session.commit()
        detail_response = (
            await client.get(f"/api/v1/workflow-jobs/{job['id']}")
        ).json()["data"]
        assert detail_response["artifacts"][0]["kind"] == "final_video"
