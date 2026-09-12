from contextlib import asynccontextmanager

import pytest
import pytest_asyncio

from src.core.exceptions import ValidationException
from src.domain.enums import PlatformType
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.publishing import PublishingJobModel, SocialAccountModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel
from src.schemas.publishing import PublishingJobCreate
from src.services.publishing_service import PublishingService
from src.storage.local_storage import LocalStorageService
from src.tasks.manager import TaskManager


@pytest_asyncio.fixture
async def publishing_fixture(test_session):
    test_session.add(ProjectModel(id="controls-project", name="Controls"))
    test_session.add(SocialAccountModel(id="controls-account", platform="douyin", account_name="Test"))
    task = TaskModel(id="controls-task", project_id="controls-project", title="旧标题", status="completed",
                     result_payload={"final_video_asset_id": "controls-video", "final_video_url": "/old.mp4"})
    test_session.add(task)
    test_session.add(AssetModel(id="controls-video", project_id=task.project_id, asset_type="video",
                               file_name="video.mp4", file_path="video.mp4", mime_type="video/mp4",
                               metadata_json={"task_id": task.id}))
    pub = PublishingJobModel(id="controls-pub", project_id=task.project_id, account_id="controls-account",
                             video_asset_id="controls-video", platform="douyin", title="发布标题", status="queued")
    test_session.add(pub)
    await test_session.commit()
    return task, pub


@pytest.mark.asyncio
async def test_cancel_queued_record_without_workflow(client, publishing_fixture):
    task, pub = publishing_fixture
    response = await client.post(f"/api/v1/publishing/jobs/{pub.id}/cancel")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"
    assert task.status == "completed"


@pytest.mark.asyncio
async def test_delete_cancels_queue_but_preserves_video_and_task(client, test_session, publishing_fixture):
    task, pub = publishing_fixture
    job = WorkflowJobModel(id="controls-job", task_id=task.id, job_type="publish", status="queued",
                           params={"publishing_job_id": pub.id})
    test_session.add(job)
    await test_session.commit()
    response = await client.delete(f"/api/v1/publishing/jobs/{pub.id}")
    assert response.status_code == 200
    assert await test_session.get(PublishingJobModel, pub.id) is None
    assert (await test_session.get(WorkflowJobModel, job.id)).status == "cancelled"
    @asynccontextmanager
    async def sessions():
        yield test_session
    assert await TaskManager(session_factory=sessions)._claim_job(job.id) is None
    assert await test_session.get(AssetModel, "controls-video") is not None
    assert (await test_session.get(TaskModel, task.id)).status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["publishing", "published", "uncertain"])
async def test_delete_rejects_inflight_or_published_records(client, test_session, publishing_fixture, status):
    _, pub = publishing_fixture
    pub.status = status
    await test_session.commit()
    response = await client.delete(f"/api/v1/publishing/jobs/{pub.id}")
    assert response.status_code == 409
    assert await test_session.get(PublishingJobModel, pub.id) is not None


@pytest.mark.asyncio
async def test_publish_records_link_to_source_video_task(client, test_session, publishing_fixture):
    task, pub = publishing_fixture
    pub.status = "published"
    await test_session.commit()
    response = await client.get("/api/v1/publishing/jobs")
    assert response.status_code == 200
    assert response.json()["data"][0]["task_id"] == task.id


@pytest.mark.asyncio
@pytest.mark.parametrize("max_retries", [0, 2])
async def test_publish_failure_does_not_fail_completed_video(test_session, publishing_fixture, max_retries):
    task, pub = publishing_fixture
    job = WorkflowJobModel(id="controls-job", task_id=task.id, job_type="publish", status="queued",
                           params={"publishing_job_id": pub.id}, max_retries=max_retries)
    test_session.add(job)
    await test_session.commit()
    @asynccontextmanager
    async def sessions():
        yield test_session
    manager = TaskManager(session_factory=sessions)
    claimed = await manager._claim_job(job.id)
    await manager._fail_or_retry(job.id, "发布失败", lease_token=claimed.lease_token)
    assert task.status == "completed"
    assert task.error_message is None
    assert job.status == ("retrying" if max_retries else "failed")


@pytest.mark.asyncio
async def test_task_detail_excludes_publish_workflow(client, test_session, publishing_fixture):
    task, pub = publishing_fixture
    test_session.add(WorkflowJobModel(id="controls-job", task_id=task.id, job_type="publish", status="running",
                                     params={"publishing_job_id": pub.id}))
    await test_session.commit()
    response = await client.get(f"/api/v1/tasks/{task.id}")
    assert response.status_code == 200
    assert response.json()["data"]["active_job"] is None
    assert response.json()["data"]["status"] == "completed"


@pytest_asyncio.fixture
async def prepare_publishing_fixture(test_session, tmp_path):
    storage = LocalStorageService(base_storage_dir=tmp_path / "storage")
    project = ProjectModel(id="prepare-project", name="Prepare")
    other_project = ProjectModel(id="prepare-other", name="Other")
    account = SocialAccountModel(id="prepare-account", platform="douyin", account_name="Test")
    task = TaskModel(
        id="prepare-task",
        project_id=project.id,
        title="任务标题",
        status="completed",
        result_payload={"final_video_asset_id": "prepare-video"},
    )
    test_session.add_all([project, other_project, account, task])

    assets = {
        "prepare-video": (project.id, "video", "video.mp4", b"video"),
        "prepare-foreign-video": (other_project.id, "video", "foreign-video.mp4", b"video"),
        "prepare-image-as-video": (project.id, "image", "image.png", b"image"),
        "prepare-missing-video": (project.id, "video", "missing-video.mp4", None),
        "prepare-cover": (project.id, "image", "cover.png", b"image"),
        "prepare-foreign-cover": (other_project.id, "image", "foreign-cover.png", b"image"),
        "prepare-video-as-cover": (project.id, "video", "video-cover.mp4", b"video"),
        "prepare-missing-cover": (project.id, "image", "missing-cover.png", None),
    }
    for asset_id, (asset_project_id, asset_type, file_name, content) in assets.items():
        file_path = f"projects/{asset_project_id}/{asset_id}-{file_name}"
        if content is not None:
            path = storage.get_path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        test_session.add(
            AssetModel(
                id=asset_id,
                project_id=asset_project_id,
                asset_type=asset_type,
                file_name=file_name,
                file_path=file_path,
                mime_type="image/png" if asset_type == "image" else "video/mp4",
                file_size_bytes=len(content or b""),
            )
        )
    await test_session.commit()
    return PublishingService(test_session, storage=storage), task


@pytest.mark.asyncio
async def test_publish_asset_boundaries_are_validated_at_both_entry_points(prepare_publishing_fixture):
    service, task = prepare_publishing_fixture

    video_checks = [
        ("prepare-foreign-video", "当前项目"),
        ("prepare-image-as-video", "类型必须"),
        ("prepare-missing-video", "不存在或为空"),
    ]
    for asset_id, message in video_checks:
        task.result_payload = {"final_video_asset_id": asset_id}
        with pytest.raises(ValidationException, match=message):
            await service.prepare_task_publishing(task.id, account_id="prepare-account")

    task.result_payload = {"final_video_asset_id": "prepare-video"}
    cover_checks = [
        ("prepare-foreign-cover", "当前项目"),
        ("prepare-video-as-cover", "类型必须"),
        ("prepare-missing-cover", "不存在或为空"),
    ]
    for asset_id, message in cover_checks:
        with pytest.raises(ValidationException, match=message):
            await service.prepare_task_publishing(
                task.id,
                account_id="prepare-account",
                cover_asset_id=asset_id,
            )

    with pytest.raises(ValidationException, match="视频素材不存在或已被删除"):
        await service.create_publishing_job(
            PublishingJobCreate(
                project_id=task.project_id,
                video_asset_id="missing-video",
                account_id="prepare-account",
                platform=PlatformType.DOUYIN,
                title="标题",
            )
        )


@pytest.mark.asyncio
async def test_prepare_normalizes_explicit_platform_metadata(prepare_publishing_fixture):
    service, task = prepare_publishing_fixture
    job = await service.prepare_task_publishing(
        task.id,
        account_id="prepare-account",
        title="《超长标题超长标题超长标题超长标题超长标题超长标题》",
        description=" 文案 " * 400,
        tags=["*#科技*", "科技", "`AI`", "#科普", "知识", "额外"],
        custom_params={"declaration": "不受支持", "visibility": "private"},
    )

    assert len(job.title) <= 30
    assert len(job.description) <= 1000
    assert job.tags == ["科技", "AI", "科普", "知识", "额外"]
    assert job.custom_params["declaration"] == ""
    assert job.custom_params["visibility"] == "private"
