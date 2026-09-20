import pytest
from sqlalchemy.exc import IntegrityError

from src.models.drama import DramaCharacterModel
from src.models.product import ProductModel
from src.models.production_context import ProductionContextSnapshotModel
from src.models.workflow import WorkflowJobModel


def knowledge_project(name="Knowledge"):
    return {"name": name, "mode": "knowledge", "knowledge_profile": {"domain": "science"}}


@pytest.mark.asyncio
async def test_project_owns_mode_and_knowledge_project_has_many_tasks(client):
    project = (await client.post("/api/v1/projects", json=knowledge_project())).json()["data"]
    for topic in ("量子", "天文"):
        response = await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": topic, "detail": {"type": "knowledge", "topic": topic}},
        )
        assert response.status_code == 201, response.text
        assert "production_mode" not in response.json()["data"]
    tasks = (await client.get(f"/api/v1/projects/{project['id']}/tasks")).json()["data"]
    assert {task["detail"]["topic"] for task in tasks} == {"量子", "天文"}


@pytest.mark.asyncio
async def test_task_rejects_mode_and_mismatched_detail(client):
    project = (await client.post("/api/v1/projects", json=knowledge_project())).json()["data"]
    invalid_mode = await client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={
            "title": "bad",
            "production_mode": "commerce",
            "detail": {"type": "knowledge", "topic": "bad"},
        },
    )
    assert invalid_mode.status_code == 422
    mismatch = await client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        json={"title": "bad", "detail": {"type": "commerce", "creative_angle": "demo"}},
    )
    assert mismatch.status_code == 422


@pytest.mark.asyncio
async def test_drama_episode_number_unique_per_project(client):
    project = (
        await client.post(
            "/api/v1/projects",
            json={
                "name": "Drama",
                "mode": "drama",
                "drama_profile": {"series_title": "Series"},
                "drama_style_guide": {},
            },
        )
    ).json()["data"]
    payload = {"title": "Episode", "detail": {"type": "drama", "episode_number": 1}}
    assert (
        await client.post(f"/api/v1/projects/{project['id']}/tasks", json=payload)
    ).status_code == 201
    with pytest.raises(IntegrityError):
        await client.post(f"/api/v1/projects/{project['id']}/tasks", json=payload)


@pytest.mark.asyncio
async def test_commerce_project_has_one_product_and_many_angles(client, test_session):
    project = (await client.post("/api/v1/projects", json={
        "name": "Commerce", "mode": "commerce",
        "commerce_profile": {"brand": "Demo"},
    })).json()["data"]
    test_session.add(ProductModel(
        id="product_main", project_id=project["id"], title="Main product"
    ))
    await test_session.commit()
    for angle in ("demo", "pain_point"):
        response = await client.post(f"/api/v1/projects/{project['id']}/tasks", json={
            "title": angle,
            "detail": {"type": "commerce", "creative_angle": angle},
        })
        assert response.status_code == 201, response.text
    tasks = (await client.get(f"/api/v1/projects/{project['id']}/tasks")).json()["data"]
    assert {task["detail"]["creative_angle"] for task in tasks} == {"demo", "pain_point"}
    test_session.add(ProductModel(
        id="product_second", project_id=project["id"], title="Forbidden second product"
    ))
    with pytest.raises(IntegrityError):
        await test_session.commit()


@pytest.mark.asyncio
async def test_unapproved_drama_resources_cannot_enter_snapshot(client, test_session, monkeypatch):
    project = (await client.post("/api/v1/projects", json={
        "name": "Drama", "mode": "drama",
        "drama_profile": {"series_title": "Series"}, "drama_style_guide": {},
    })).json()["data"]
    task = (await client.post(f"/api/v1/projects/{project['id']}/tasks", json={
        "title": "Episode 1", "detail": {"type": "drama", "episode_number": 1},
    })).json()["data"]
    test_session.add(DramaCharacterModel(
        id="char_pending", project_id=project["id"], name="Pending character"
    ))
    await test_session.commit()
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {"llm": {"provider_id": "test"}}

    monkeypatch.setattr("src.services.provider_manager.ProviderManager.capture_snapshot", providers)
    response = await client.post(f"/api/v1/tasks/{task['id']}/jobs")
    assert response.status_code == 422
    assert "必须先通过审批" in response.text


@pytest.mark.asyncio
async def test_new_production_gets_new_snapshot_and_retry_reuses_original(
    client, test_session, monkeypatch
):
    project = (await client.post("/api/v1/projects", json=knowledge_project())).json()["data"]
    task = (
        await client.post(
            f"/api/v1/projects/{project['id']}/tasks",
            json={"title": "one", "detail": {"type": "knowledge", "topic": "one"}},
        )
    ).json()["data"]
    await client.post(f"/api/v1/tasks/{task['id']}/approve")

    async def providers(self, **kwargs):
        return {"llm": {"provider_id": "test"}}

    monkeypatch.setattr("src.services.provider_manager.ProviderManager.capture_snapshot", providers)
    first = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    first_model = await test_session.get(WorkflowJobModel, first["id"])
    snapshot = await test_session.get(
        ProductionContextSnapshotModel, first_model.production_context_snapshot_id
    )
    first_model.status = "failed"
    await test_session.commit()
    await client.patch(f"/api/v1/tasks/{task['id']}", json={"title": "changed"})
    retry = (await client.post(f"/api/v1/workflow-jobs/{first['id']}/retry")).json()["data"]
    retry_model = await test_session.get(WorkflowJobModel, retry["id"])
    assert retry_model.production_context_snapshot_id == snapshot.id
    assert snapshot.context_payload["task"]["title"] == "one"
    retry_model.status = "failed"
    await test_session.commit()
    second = (await client.post(f"/api/v1/tasks/{task['id']}/jobs")).json()["data"]
    second_model = await test_session.get(WorkflowJobModel, second["id"])
    assert second_model.production_context_snapshot_id != snapshot.id
    new_snapshot = await test_session.get(
        ProductionContextSnapshotModel, second_model.production_context_snapshot_id
    )
    assert new_snapshot.context_payload["task"]["title"] == "changed"
    assert new_snapshot.context_hash != snapshot.context_hash
