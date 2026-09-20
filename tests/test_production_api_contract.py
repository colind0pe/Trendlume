from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.api.app import create_app
from src.models.workflow import WorkflowArtifactModel, WorkflowStepRunModel


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
