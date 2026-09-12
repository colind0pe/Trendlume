from __future__ import annotations

import json
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.domain.enums import (
    AccountStatus,
    AssetType,
    JobStatus,
    PlatformType,
    PublishJobStatus,
)
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.publishing import (
    CredentialModel,
    PublishingJobModel,
    SocialAccountModel,
)
from src.models.workflow import WorkflowJobModel
from src.schemas.task import ScheduledPublishConfig, TaskCreate
from src.services.asset_service import AssetService
from src.services.task_service import TaskService
from src.storage.local_storage import LocalStorageService
from src.tasks.manager import TaskManager


@pytest.mark.asyncio
async def test_asset_batch_operations_tag_archive_and_protect_references(
    test_session: AsyncSession, tmp_path
):
    project = ProjectModel(id="project_asset_batch", name="Asset batch", aspect_ratio="9:16")
    test_session.add(project)
    await test_session.commit()

    storage = LocalStorageService(base_storage_dir=tmp_path / "asset-storage")
    service = AssetService(test_session, storage=storage)
    free_asset = await service.save_asset(
        content=b"free-asset",
        file_name="free.txt",
        mime_type="text/plain",
        asset_type=AssetType.IMAGE,
        project_id=project.id,
        metadata={"tags": ["已有"]},
    )
    protected_asset = await service.save_asset(
        content=b"protected-asset",
        file_name="protected.txt",
        mime_type="text/plain",
        asset_type=AssetType.IMAGE,
        project_id=project.id,
    )
    system_asset = await service.save_asset(
        content=b"system-asset",
        file_name="system.txt",
        mime_type="text/plain",
        asset_type=AssetType.BGM,
        metadata={"scope": "system"},
    )
    project.cover_asset_id = protected_asset.id
    await test_session.commit()

    tagged = await service.batch_tag_assets(
        [free_asset.id, protected_asset.id, system_asset.id],
        ["#科技", "科技", "待用"],
    )
    assert set(tagged["updated_ids"]) == {free_asset.id, protected_asset.id}
    assert tagged["skipped"] == [{"id": system_asset.id, "reason": "system_asset"}]
    await test_session.refresh(free_asset)
    assert free_asset.metadata_json["tags"] == ["已有", "科技", "待用"]

    archive = await service.build_asset_archive([free_asset.id, protected_asset.id, "missing"])
    with zipfile.ZipFile(archive) as archive_file:
        names = set(archive_file.namelist())
        assert f"{free_asset.id}_free.txt" in names
        assert f"{protected_asset.id}_protected.txt" in names
        manifest = json.loads(archive_file.read("manifest.json"))
    assert {item["asset_id"] for item in manifest if item["status"] == "included"} == {
        free_asset.id,
        protected_asset.id,
    }
    assert {item["asset_id"] for item in manifest if item["status"] == "skipped"} == {"missing"}

    deleted = await service.batch_delete_assets(
        [free_asset.id, protected_asset.id, system_asset.id]
    )
    assert deleted["deleted_ids"] == [free_asset.id]
    assert {item["reason"] for item in deleted["skipped"]} == {
        "project_reference",
        "system_asset",
    }
    assert not await storage.exists(free_asset.file_path)
    assert await test_session.get(AssetModel, free_asset.id) is None
    assert await test_session.get(AssetModel, protected_asset.id) is not None


@pytest.mark.asyncio
async def test_task_schedule_persists_and_generation_completion_enqueues_once(
    test_session: AsyncSession, tmp_path, monkeypatch
):
    project = ProjectModel(id="project_auto_publish", name="Auto publish", aspect_ratio="9:16")
    credential = CredentialModel(
        id="credential_auto_publish",
        platform=PlatformType.DOUYIN.value,
        payload={"cookies": [{"name": "sessionid", "value": "test"}]},
        is_valid=True,
    )
    account = SocialAccountModel(
        id="account_auto_publish",
        platform=PlatformType.DOUYIN.value,
        account_name="测试抖音号",
        username="auto_publish",
        status=AccountStatus.ACTIVE.value,
        credential_id=credential.id,
    )
    test_session.add_all([project, credential, account])
    await test_session.commit()

    scheduled_at = datetime.now(UTC) + timedelta(hours=2)
    task = await TaskService(test_session).create_task(
        project.id,
        TaskCreate(
            title="定时发布任务",
            target_scene_count=12,
            scheduled_publish=ScheduledPublishConfig(
                account_id=account.id,
                scheduled_at=scheduled_at,
                timezone="Asia/Shanghai",
            ),
        ),
    )
    persisted_config = task.input_payload["scheduled_publish"]
    assert task.input_payload["target_scene_count"] == 12
    assert persisted_config["status"] == "pending"
    assert persisted_config["account_id"] == account.id
    assert persisted_config["timezone"] == "Asia/Shanghai"
    assert persisted_config["scheduled_at"].endswith("+00:00")

    storage = LocalStorageService(base_storage_dir=tmp_path / "publish-storage")
    monkeypatch.setattr(
        "src.services.publishing_service.local_storage.base_dir",
        storage.base_dir,
    )
    video_asset = await AssetService(test_session, storage=storage).save_asset(
        content=(Path(__file__).parent / "fixtures" / "mock.mp4").read_bytes(),
        file_name="generated.mp4",
        mime_type="video/mp4",
        asset_type=AssetType.VIDEO,
        project_id=project.id,
    )
    task.result_payload = {"final_video_asset_id": video_asset.id}
    await test_session.commit()

    @asynccontextmanager
    async def session_factory():
        yield test_session

    manager = TaskManager(num_workers=0, session_factory=session_factory)
    await manager._enqueue_scheduled_publish(task.id)

    publishing_jobs = list(
        (
            await test_session.execute(
                select(PublishingJobModel).where(PublishingJobModel.project_id == project.id)
            )
        ).scalars()
    )
    workflow_jobs = list(
        (
            await test_session.execute(
                select(WorkflowJobModel).where(WorkflowJobModel.task_id == task.id)
            )
        ).scalars()
    )
    assert len(publishing_jobs) == 1
    assert publishing_jobs[0].status == PublishJobStatus.SCHEDULED.value
    assert publishing_jobs[0].custom_params["auto_scheduled"] is True
    assert publishing_jobs[0].custom_params["source_task_id"] == task.id
    assert len(workflow_jobs) == 1
    assert workflow_jobs[0].status == JobStatus.QUEUED.value
    assert workflow_jobs[0].scheduled_at is not None

    await test_session.refresh(task)
    assert task.input_payload["scheduled_publish"]["status"] == "scheduled"
    assert task.input_payload["scheduled_publish"]["publishing_job_id"] == publishing_jobs[0].id

    # Re-running the completion hook must not create a duplicate publishing job.
    await manager._enqueue_scheduled_publish(task.id)
    publishing_jobs_after_retry = list(
        (
            await test_session.execute(
                select(PublishingJobModel).where(PublishingJobModel.project_id == project.id)
            )
        ).scalars()
    )
    assert len(publishing_jobs_after_retry) == 1

    cancelled = await manager.cancel_publishing_workflow(
        publishing_jobs_after_retry[0].id,
        session_factory=session_factory,
    )
    assert cancelled is True
    await test_session.refresh(task)
    await test_session.refresh(publishing_jobs_after_retry[0])
    await test_session.refresh(workflow_jobs[0])
    assert task.input_payload["scheduled_publish"]["status"] == "cancelled"
    assert publishing_jobs_after_retry[0].status == PublishJobStatus.CANCELLED.value
    assert workflow_jobs[0].status == JobStatus.CANCELLED.value
