from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.database import Base
from src.domain.enums import JobStatus, JobType, TaskStatus
from src.models.project import ProjectModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel
from src.tasks.broadcaster import event_broadcaster
from src.tasks.manager import TaskManager


class FastExecutor:
    async def execute(self, job):
        return {"checkpoint": "ok", "job_id": job.id}


class SlowExecutor:
    def __init__(self):
        self.started = asyncio.Event()

    async def execute(self, job):
        self.started.set()
        await asyncio.Event().wait()
        return {"checkpoint": "finished"}


@pytest_asyncio.fixture
async def durable_sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'durable.db').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield sessions
    finally:
        await engine.dispose()


async def _seed_task(sessions, *, task_id, project_id, title, status=TaskStatus.DRAFT.value):
    async with sessions() as session:
        session.add(ProjectModel(id=project_id, name=title))
        session.add(TaskModel(id=task_id, project_id=project_id, title=title, status=status))
        await session.commit()


def _event_types(queue):
    event_types = []
    while not queue.empty():
        message = queue.get_nowait()
        event_types.append(json.loads(message.split("data:", 1)[1].strip())["event"])
    return event_types


@pytest.mark.asyncio
async def test_workflow_job_survives_manager_restart(durable_sessions):
    sessions = durable_sessions
    await _seed_task(
        sessions,
        task_id="t_durable",
        project_id="p_durable",
        title="Durable task",
    )

    manager = TaskManager(num_workers=1, session_factory=sessions, executor=FastExecutor())
    await manager.start()
    queue = event_broadcaster.subscribe(task_id="t_durable")
    submitted = await manager.submit_task("t_durable")
    await asyncio.wait_for(manager.queue.join(), timeout=3)
    completed = await manager.get_job(submitted.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED.value
    await manager.stop()
    event_types = _event_types(queue)
    event_broadcaster.unsubscribe(queue)
    assert "job.started" in event_types
    assert "job.completed" in event_types

    # A second manager sees the same durable record; no in-memory registry is required.
    restarted = TaskManager(num_workers=1, session_factory=sessions, executor=FastExecutor())
    latest = await restarted.get_latest_job("t_durable")
    assert latest is not None
    assert latest.status == JobStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_cancel_task_emits_job_and_task_events(durable_sessions):
    sessions = durable_sessions
    await _seed_task(
        sessions,
        task_id="t_cancel_events",
        project_id="p_cancel_events",
        title="Cancel task",
    )

    manager = TaskManager(num_workers=1, session_factory=sessions, executor=SlowExecutor())
    queue = event_broadcaster.subscribe(task_id="t_cancel_events")
    await manager.start()
    await manager.submit_task("t_cancel_events")
    await asyncio.wait_for(manager.executor.started.wait(), timeout=1)
    await manager.cancel_task("t_cancel_events")
    await manager.stop()

    event_types = _event_types(queue)
    event_broadcaster.unsubscribe(queue)
    assert "job.cancelled" in event_types
    assert "task.cancelled" in event_types


@pytest.mark.asyncio
async def test_stale_running_job_is_requeued_from_checkpoint(durable_sessions):
    sessions = durable_sessions
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    await _seed_task(
        sessions,
        task_id="t_stale",
        project_id="p_stale",
        title="Stale task",
        status=TaskStatus.RUNNING.value,
    )
    async with sessions() as session:
        session.add(WorkflowJobModel(
            id="job_stale", task_id="t_stale", job_type=JobType.FULL_PIPELINE.value,
            status=JobStatus.RUNNING.value, current_stage="visuals", progress=55,
            params={}, checkpoint={"stage": "visuals"}, available_at=old,
            heartbeat_at=old, created_at=old, updated_at=old,
        ))
        await session.commit()

    manager = TaskManager(num_workers=1, session_factory=sessions, executor=FastExecutor())
    await manager._recover_stale_jobs()
    async with sessions() as session:
        job = await session.get(WorkflowJobModel, "job_stale")
        assert job is not None
        assert job.status == JobStatus.QUEUED.value
        assert job.current_stage == "visuals"
        assert job.checkpoint["stage"] == "visuals"


@pytest.mark.asyncio
async def test_job_events_are_replayable(durable_sessions):
    sessions = durable_sessions
    now = datetime.now(UTC).replace(tzinfo=None)
    await _seed_task(
        sessions,
        task_id="t_events",
        project_id="p_events",
        title="Events task",
    )
    async with sessions() as session:
        session.add(WorkflowJobModel(
            id="job_events", task_id="t_events", job_type=JobType.FULL_PIPELINE.value,
            status=JobStatus.QUEUED.value, current_stage="queued", progress=0,
            params={}, checkpoint={}, available_at=now, created_at=now, updated_at=now,
        ))
        await session.commit()
    event_broadcaster.bind_job("t_events", "job_events", sessions)
    queue = event_broadcaster.subscribe(task_id="t_events")
    await event_broadcaster.broadcast(
        "step.completed",
        {
            "task_id": "t_events",
            "job_id": "job_events",
            "stage": "visuals",
            "status": JobStatus.RUNNING.value,
            "progress": 10,
            "message": "正在生成视觉素材",
        },
        task_id="t_events",
        job_id="job_events",
    )
    await event_broadcaster.broadcast(
        "step.completed",
        {
            "task_id": "t_events",
            "job_id": "job_events",
            "stage": "visuals",
            "status": JobStatus.RUNNING.value,
            "progress": 20,
            "message": "视觉素材生成完成",
        },
        task_id="t_events",
        job_id="job_events",
    )
    live_message = await asyncio.wait_for(queue.get(), timeout=1)
    live_envelope = json.loads(live_message.split("data:", 1)[1].strip())
    assert live_envelope["event"] == "step.completed"
    assert isinstance(live_envelope["event_id"], int)
    assert live_envelope["created_at"]
    assert live_envelope["data"]["task_id"] == "t_events"
    assert live_envelope["data"]["job_id"] == "job_events"
    event_broadcaster.unsubscribe(queue)
    replay = await event_broadcaster.replay("t_events", 0)
    assert len(replay) == 2
    first_id = int(replay[0].split("\n", 1)[0].split(":", 1)[1].strip())
    assert len(await event_broadcaster.replay("t_events", first_id)) == 1
