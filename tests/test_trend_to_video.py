from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.project import ProjectModel
from src.models.trend import TopicProposalModel
from src.models.workflow import WorkflowJobModel
from src.services.durable_pipeline import build_script_generation_inputs
from src.services.trend_service import TrendService
from src.services.trend_sources import TrendSourceItem, TrendSourceResult


def _source(title: str = "AI 热点") -> TrendSourceResult:
    return TrendSourceResult(
        source_key="proposal-fixture",
        adapter_name="test-fixture",
        platform="weibo",
        status="fresh",
        fetched_at=datetime.now(UTC),
        items=(
            TrendSourceItem(
                title=title,
                rank=1,
                raw_metric="1.2万",
                metric_unit="次",
                source_url="https://example.com/trend",
            ),
        ),
    )


async def _persist_source(test_session: AsyncSession, title: str = "AI 热点") -> None:
    await TrendService(test_session).persist_results([_source(title)])


@pytest.mark.asyncio
async def test_proposal_revision_and_task_are_idempotent(
    client, test_session: AsyncSession
):
    project = ProjectModel(
        id="proposal-project",
        name="Proposal project",
        settings={"trends": {"include_keywords": ["AI"]}},
    )
    test_session.add(project)
    await test_session.commit()
    await _persist_source(test_session)
    feed = await client.get("/api/v1/trends", params={"freshness": "all"})
    trend_item_id = feed.json()["data"]["items"][0]["id"]

    created = await client.post(
        "/api/v1/trends/proposals",
        json={"project_id": project.id, "trend_item_id": trend_item_id},
    )
    assert created.status_code == 201
    proposal = created.json()["data"]
    assert proposal["revision"] == 1
    assert proposal["trend_snapshot"]["source_url"] == "https://example.com/trend"
    assert proposal["generation_options"]["content_mode"] == "generated_image"
    assert proposal["generation_options"]["genre"] == "auto"
    assert proposal["generation_options"]["bgm_enabled"] is True
    assert proposal["knowledge_brief"]["thesis"]
    assert proposal["knowledge_brief"]["source_refs"] == ["https://example.com/trend"]
    again = await client.post(
        "/api/v1/trends/proposals",
        json={"project_id": project.id, "trend_item_id": trend_item_id},
    )
    assert again.json()["data"]["id"] == proposal["id"]

    changed = await client.patch(
        f"/api/v1/trends/proposals/{proposal['id']}",
        json={"expected_revision": 1, "angle": "从项目视角解释 AI 热点"},
    )
    assert changed.status_code == 200
    proposal = changed.json()["data"]
    assert proposal["revision"] == 2
    stale = await client.patch(
        f"/api/v1/trends/proposals/{proposal['id']}",
        json={"expected_revision": 1, "angle": "过期编辑"},
    )
    assert stale.status_code == 409

    approved = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/approve-and-create-task",
        json={"expected_revision": proposal["revision"]},
    )
    assert approved.status_code == 200
    action = approved.json()["data"]
    assert action["task"]["id"]
    assert action["task"]["production_mode"] == "knowledge"
    assert action["proposal"]["status"] == "task_created"
    task_id = action["task"]["id"]
    assert (
        action["task"]["input_payload"]["trend_provenance"]["proposal_id"]
        == proposal["id"]
    )
    assert action["task"]["input_payload"]["enable_research"] is True
    assert action["task"]["input_payload"]["content_mode"] == "generated_image"
    assert action["task"]["input_payload"]["voice_speed"] == 1.0
    assert action["task"]["input_payload"]["knowledge_brief"]["thesis"]
    script_inputs = build_script_generation_inputs(
        action["task"]["input_payload"], topic=action["task"]["title"]
    )
    assert script_inputs["knowledge_brief"]["key_claims"][0]["statement"] == "AI 热点"

    repeated = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/approve-and-create-task",
        json={"expected_revision": proposal["revision"]},
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["task"]["id"] == task_id
    assert len((await test_session.scalars(select(TopicProposalModel))).all()) == 1


@pytest.mark.asyncio
async def test_proposal_generation_options_are_carried_into_task(
    client, test_session: AsyncSession
):
    project = ProjectModel(
        id="proposal-options-project", name="Proposal options", settings={}
    )
    test_session.add(project)
    await test_session.commit()
    await _persist_source(test_session, "可配置热点")
    feed = await client.get("/api/v1/trends", params={"freshness": "all"})
    trend_item_id = feed.json()["data"]["items"][0]["id"]

    proposal = (
        await client.post(
            "/api/v1/trends/proposals",
            json={"project_id": project.id, "trend_item_id": trend_item_id},
        )
    ).json()["data"]
    edited = await client.patch(
        f"/api/v1/trends/proposals/{proposal['id']}",
        json={
            "expected_revision": proposal["revision"],
            "generation_options": {
                "content_mode": "generated_video",
                "template_id": "video_full_overlay",
                "genre": "culture_history",
                "hook_type": "curiosity_gap",
                "style_preset": "cinematic_real",
                "prompt_prefix": "低饱和纪实摄影",
                "voice_id": "zh-CN-YunxiNeural",
                "speed": 1.2,
                "bgm_enabled": False,
                "bgm_volume": 0.1,
            },
        },
    )
    assert edited.status_code == 200

    approved = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/approve-and-create-task",
        json={"expected_revision": edited.json()["data"]["revision"]},
    )
    assert approved.status_code == 200
    task_payload = approved.json()["data"]["task"]["input_payload"]
    assert task_payload["content_mode"] == "generated_video"
    assert task_payload["template_id"] == "video_full_overlay"
    assert task_payload["genre"] == "culture_history"
    assert task_payload["hook_type"] == "curiosity_gap"
    assert task_payload["style_preset"] == "cinematic_real"
    assert task_payload["prompt_prefix"] == "低饱和纪实摄影"
    assert task_payload["voice_id"] == "zh-CN-YunxiNeural"
    assert task_payload["speed"] == 1.2
    assert task_payload["voice_speed"] == 1.2
    assert task_payload["bgm_enabled"] is False
    assert task_payload["bgm_asset_id"] is None
    assert task_payload["bgm_volume"] == 0.1


@pytest.mark.asyncio
async def test_approve_and_run_keeps_task_when_queue_fails(
    client, test_session: AsyncSession, monkeypatch
):
    project = ProjectModel(id="queue-project", name="Queue project", settings={})
    test_session.add(project)
    await test_session.commit()
    await _persist_source(test_session, "队列失败热点")
    feed = await client.get("/api/v1/trends", params={"freshness": "all"})
    trend_item_id = feed.json()["data"]["items"][0]["id"]
    proposal = (
        await client.post(
            "/api/v1/trends/proposals",
            json={"project_id": project.id, "trend_item_id": trend_item_id},
        )
    ).json()["data"]

    async def fail_queue(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    from src.api.routes import trends as trends_route

    monkeypatch.setattr(trends_route.task_manager, "submit_task", fail_queue)
    response = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/approve-and-run",
        json={"expected_revision": proposal["revision"]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["queue_status"] == "failed"
    assert data["proposal"]["status"] == "queue_failed"
    assert data["task"]["id"]
    assert "queue unavailable" in data["task"]["error_message"]

    class FakeJob:
        def to_dict(self):
            return {
                "id": "job-fixture",
                "task_id": data["task"]["id"],
                "status": "queued",
            }

    async def queue_ok(*args, **kwargs):
        return FakeJob()

    monkeypatch.setattr(trends_route.task_manager, "submit_task", queue_ok)
    retried = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/approve-and-run",
        json={"expected_revision": proposal["revision"]},
    )
    assert retried.status_code == 200
    assert retried.json()["data"]["queue_status"] == "queued"
    assert retried.json()["data"]["proposal"]["status"] == "task_created"


@pytest.mark.asyncio
async def test_approve_and_run_commits_before_existing_queue(
    client, test_session: AsyncSession
):
    project = ProjectModel(
        id="queue-success-project", name="Queue success", settings={}
    )
    test_session.add(project)
    await test_session.commit()
    await _persist_source(test_session, "排队成功热点")
    feed = await client.get("/api/v1/trends", params={"freshness": "all"})
    trend_item_id = feed.json()["data"]["items"][0]["id"]
    proposal = (
        await client.post(
            "/api/v1/trends/proposals",
            json={"project_id": project.id, "trend_item_id": trend_item_id},
        )
    ).json()["data"]
    response = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/approve-and-run",
        json={"expected_revision": proposal["revision"]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["queue_status"] == "queued"
    assert data["job"]["task_id"] == data["task"]["id"]
    job = await test_session.get(WorkflowJobModel, data["job"]["id"])
    assert job is not None
    assert job.task_id == data["task"]["id"]


@pytest.mark.asyncio
async def test_reject_proposal(client, test_session: AsyncSession):
    project = ProjectModel(id="reject-project", name="Reject project", settings={})
    test_session.add(project)
    await test_session.commit()
    await _persist_source(test_session, "拒绝热点")
    feed = await client.get("/api/v1/trends", params={"freshness": "all"})
    trend_item_id = feed.json()["data"]["items"][0]["id"]
    proposal = (
        await client.post(
            "/api/v1/trends/proposals",
            json={"project_id": project.id, "trend_item_id": trend_item_id},
        )
    ).json()["data"]
    rejected = await client.post(
        f"/api/v1/trends/proposals/{proposal['id']}/reject",
        json={"expected_revision": proposal["revision"]},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"
