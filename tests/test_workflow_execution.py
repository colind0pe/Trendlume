from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update
from src.core.exceptions import TrendlumeException
from src.models import ProjectModel, TaskModel
from src.models.scene import SceneModel
from src.models.workflow import WorkflowJobModel, WorkflowStepRunModel
from src.schemas.scene import SceneUpdate
from src.schemas.task import TaskUpdate
from src.services.scene_service import SceneService
from src.services.task_service import TaskService
from src.services.workflow_execution import WorkflowLeaseLost
from src.tasks.broadcaster import EventBroadcaster
from src.tasks.manager import TaskManager


async def setup(db):
    project = ProjectModel(id=str(uuid4()), name="Lease test")
    db.add(project)
    await db.flush()
    task = TaskModel(id=str(uuid4()), project_id=project.id, title="original")
    db.add(task)
    await db.flush()
    scene = SceneModel(id=str(uuid4()), task_id=task.id, sequence_index=0, narration_text="original")
    db.add(scene)
    await db.commit()
    @asynccontextmanager
    async def factory():
        yield db
    return TaskManager(session_factory=factory), task, scene


@pytest.mark.asyncio
async def test_reclaimed_lease_rejects_old_mutations_and_dirty_flush(test_session):
    manager, task, _ = await setup(test_session)
    job = await manager.submit_task(task.id)
    claimed = await manager._claim_job(job.id)
    old = claimed.lease_token
    await test_session.execute(update(WorkflowJobModel).where(WorkflowJobModel.id == job.id)
        .values(status="queued", lease_token=None))
    await test_session.commit()
    test_session.expire(claimed)
    new = await manager._claim_job(job.id)
    assert new.lease_token != old
    task_id = task.id
    for operation in (
        lambda: manager.heartbeat(job.id, lease_token=old),
        lambda: manager._finish_job(job.id, {}, lease_token=old),
        lambda: manager._fail_or_retry(job.id, "late failure", lease_token=old),
        lambda: manager._requeue_interrupted(job.id, lease_token=old),
    ):
        task = await test_session.get(TaskModel, task_id)
        task.title = "must not flush"
        with pytest.raises(WorkflowLeaseLost):
            await operation()
        assert (await test_session.get(TaskModel, task_id)).title == "original"
        assert (await test_session.get(WorkflowJobModel, job.id)).status == "running"


@pytest.mark.asyncio
async def test_busy_edit_conflict_and_manual_edit_after_cancel(test_session):
    manager, task, scene = await setup(test_session)
    task_id, scene_id = task.id, scene.id
    await manager.submit_task(task_id)
    with pytest.raises(TrendlumeException) as error:
        await SceneService(test_session).update_scene(scene_id, SceneUpdate(narration_text="new"))
    assert error.value.status_code == 409
    await test_session.rollback()
    with pytest.raises(TrendlumeException) as error:
        await manager.submit_task(task_id)
    assert error.value.status_code == 409
    await test_session.rollback()
    await manager.cancel_task(task_id)
    await SceneService(test_session).update_scene(scene_id, SceneUpdate(narration_text="new"))
    await test_session.commit()
    assert (await test_session.get(TaskModel, task_id)).input_payload["manual_storyboard_version"]


@pytest.mark.asyncio
async def test_stale_recovery_interrupts_steps_and_generation_has_no_job_retry(test_session):
    manager, task, scene = await setup(test_session)
    job = await manager.submit_task(task.id)
    claimed = await manager._claim_job(job.id)
    token = claimed.lease_token
    run = WorkflowStepRunModel(id=str(uuid4()), task_id=task.id, job_id=job.id,
        step_key="voice", unit_key=scene.id, attempt=1, input_fingerprint="a" * 64)
    test_session.add(run)
    await test_session.commit()
    await test_session.execute(update(WorkflowJobModel).where(WorkflowJobModel.id == job.id)
        .values(heartbeat_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)))
    await test_session.commit()
    await manager._requeue_stale_running_jobs()
    await test_session.refresh(run)
    assert run.status == "interrupted"
    test_session.expire(claimed)
    claimed = await manager._claim_job(job.id)
    assert claimed.lease_token != token
    await manager._fail_or_retry(job.id, "stage exhausted", lease_token=claimed.lease_token)
    await test_session.refresh(claimed)
    assert claimed.status == "failed" and claimed.retry_count == 0


@pytest.mark.asyncio
async def test_expired_worker_cannot_persist_or_emit_event(test_session):
    manager, task, _ = await setup(test_session)
    job = await manager.submit_task(task.id)
    claimed = await manager._claim_job(job.id)
    token = claimed.lease_token
    broadcaster = EventBroadcaster()
    broadcaster.bind_job(task.id, job.id, manager.session_factory)
    queue = broadcaster.subscribe(task_id=task.id)
    await broadcaster.broadcast("step.completed", {}, task.id, job.id, lease_token=token)
    assert not queue.empty()
    queue.get_nowait()
    await manager.cancel_task(task.id)
    event_count = len(await broadcaster.replay(job.task_id))
    with pytest.raises(WorkflowLeaseLost):
        await broadcaster.broadcast("step.completed", {}, task.id, job.id, lease_token=token)
    assert queue.empty()
    assert len(await broadcaster.replay(job.task_id)) == event_count


@pytest.mark.asyncio
async def test_task_patch_preserves_internal_snapshots_and_bgm_only_stales_composition(test_session):
    _, task, scene = await setup(test_session)
    task.input_payload = {"bgm_volume": 0.2, "workflow_provider_snapshot": {"model": "original"},
                          "manual_storyboard_version": "original"}
    job = WorkflowJobModel(id=str(uuid4()), task_id=task.id, job_type="full_pipeline", status="completed")
    test_session.add(job)
    await test_session.flush()
    voice = WorkflowStepRunModel(id=str(uuid4()), task_id=task.id, job_id=job.id,
        step_key="voice", unit_key=scene.id, attempt=1, input_fingerprint="a" * 64, status="completed")
    composition = WorkflowStepRunModel(id=str(uuid4()), task_id=task.id, job_id=job.id,
        step_key="composition", unit_key="", attempt=1, input_fingerprint="b" * 64, status="completed")
    test_session.add_all([voice, composition])
    await test_session.commit()
    await TaskService(test_session).update_task(task.id, TaskUpdate(input_payload={"bgm_volume": 0.5,
        "workflow_provider_snapshot": {"model": "forged"}, "manual_storyboard_version": "forged"}))
    assert task.input_payload["workflow_provider_snapshot"] == {"model": "original"}
    assert task.input_payload["manual_storyboard_version"] == "original"
    await test_session.refresh(voice)
    await test_session.refresh(composition)
    assert voice.validity == "valid" and composition.validity == "stale"
