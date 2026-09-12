import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from starlette.requests import Request

from src.core.database import async_session_factory
from src.models.workflow import JobEventModel


class EventBroadcaster:
    """In-memory Server-Sent Events (SSE) broadcaster supporting global and task-specific channels"""

    _DEFAULT_STATUS = {
        "job.started": "running",
        "job.progress": "running",
        "job.retrying": "retrying",
        "job.completed": "completed",
        "job.failed": "failed",
        "job.cancelled": "cancelled",
        "task.started": "running",
        "task.completed": "completed",
        "task.failed": "failed",
        "task.cancelled": "cancelled",
        "step.started": "running",
        "step.completed": "completed",
        "progress": "running",
        "scene.status_changed": "running",
        "asset.created": "created",
        "video.preview_ready": "ready",
    }

    def __init__(self):
        # Maps queue -> optional task_id filter
        self._subscribers: dict[asyncio.Queue, str | None] = {}
        self._job_bindings: dict[str, tuple[str, Any]] = {}

    def bind_job(self, task_id: str, job_id: str, session_factory=async_session_factory) -> None:
        """Associate task events with a durable job and its database session factory."""
        self._job_bindings[task_id] = (job_id, session_factory)

    def subscribe(self, task_id: str | None = None) -> asyncio.Queue:
        """Register an SSE client with an optional task-id filter."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers[queue] = task_id
        logger.debug(
            f"SSE client connected (filter={task_id}). Total active subscribers: {len(self._subscribers)}"
        )
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unregister an SSE client subscriber"""
        self._subscribers.pop(queue, None)
        logger.debug(f"SSE client disconnected. Total active subscribers: {len(self._subscribers)}")

    @classmethod
    def _normalize_data(
        cls,
        event_type: str,
        data: dict[str, Any],
        task_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Keep task events on one small, backwards-compatible payload contract."""
        payload = dict(data or {})
        if task_id:
            payload.setdefault("task_id", task_id)
        if job_id:
            payload.setdefault("job_id", job_id)

        if payload.get("task_id") or payload.get("job_id"):
            stage = payload.get("stage") or payload.get("current_stage")
            if not stage:
                stage = payload.get("step") or payload.get("current_step")
            if stage:
                payload.setdefault("stage", str(stage).lower())
            else:
                payload["stage"] = {
                    "job.completed": "completed",
                    "job.failed": "failed",
                    "job.cancelled": "cancelled",
                    "task.completed": "completed",
                    "task.failed": "failed",
                    "task.cancelled": "cancelled",
                }.get(event_type, "queued")

            payload.setdefault("status", cls._DEFAULT_STATUS.get(event_type, "running"))
            if not payload.get("message"):
                payload["message"] = payload.get("error") or payload.get("error_message")

        return payload

    @staticmethod
    def _isoformat(value: datetime | None) -> str:
        timestamp = value or datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.isoformat()

    @classmethod
    def _format_sse_message(
        cls,
        event_type: str,
        data: dict[str, Any],
        event_id: int | None = None,
        created_at: datetime | None = None,
    ) -> str:
        created_at_value = cls._isoformat(created_at)
        payload = {
            "event": event_type,
            "data": data,
            "event_id": event_id,
            "created_at": created_at_value,
            # Keep timestamp for consumers of the original event contract.
            "timestamp": created_at_value,
        }
        json_data = json.dumps(payload, ensure_ascii=False)
        event_prefix = f"id: {event_id}\n" if event_id is not None else ""
        return f"{event_prefix}event: {event_type}\ndata: {json_data}\n\n"

    async def replay(self, task_id: str, last_event_id: int = 0, limit: int = 100) -> list[str]:
        """Load persisted events for a task after the client's last SSE id."""
        binding = self._job_bindings.get(task_id)
        factory = binding[1] if binding else async_session_factory
        try:
            async with factory() as session:
                query = select(JobEventModel).where(JobEventModel.task_id == task_id)
                if last_event_id > 0:
                    query = query.where(JobEventModel.id > last_event_id).order_by(JobEventModel.id).limit(limit)
                    result = await session.execute(query)
                    events = list(result.scalars().all())
                else:
                    # Initial connection / page refresh:
                    # Replay at most the latest 50 events in chronological order to prevent flooding.
                    initial_limit = min(limit, 50)
                    query = query.order_by(JobEventModel.id.desc()).limit(initial_limit)
                    result = await session.execute(query)
                    events = list(reversed(result.scalars().all()))

                return [
                    self._format_sse_message(
                        event.event_type,
                        self._normalize_data(event.event_type, event.payload, event.task_id, event.job_id),
                        event.id,
                        event.created_at,
                    )
                    for event in events
                ]
        except Exception as exc:
            logger.warning(f"Failed to replay events for task {task_id}: {exc}")
            return []

    async def broadcast(
        self,
        event_type: str,
        data: dict[str, Any],
        task_id: str | None = None,
        job_id: str | None = None,
        *, lease_token: str | None = None,
    ) -> None:
        """Persist and broadcast an event to all interested subscribers."""
        target_task_id = task_id or data.get("task_id")
        binding = self._job_bindings.get(target_task_id) if target_task_id else None
        resolved_job_id = job_id or data.get("job_id") or (binding[0] if binding else None)
        normalized_data = self._normalize_data(event_type, data, target_task_id, resolved_job_id)
        event_id: int | None = None
        event_created_at: datetime | None = None
        if lease_token is not None and (not resolved_job_id or not binding):
            return
        if resolved_job_id and binding:
            try:
                async with binding[1]() as session:
                    if lease_token is not None:
                        from src.services.workflow_execution import WorkflowExecutionContext
                        await WorkflowExecutionContext(resolved_job_id, lease_token).fence(session)
                    event = JobEventModel(
                        job_id=resolved_job_id,
                        task_id=target_task_id or "",
                        event_type=event_type,
                        payload=normalized_data,
                    )
                    session.add(event)
                    await session.flush()
                    event_id = event.id
                    event_created_at = event.created_at
                    # Keep only the most recent 500 events for each job.
                    ids = await session.execute(
                        select(JobEventModel.id)
                        .where(JobEventModel.job_id == resolved_job_id)
                        .order_by(JobEventModel.id.desc())
                        .offset(500)
                    )
                    old_ids = [row[0] for row in ids.all()]
                    if old_ids:
                        await session.execute(delete(JobEventModel).where(JobEventModel.id.in_(old_ids)))

                    # Keep only the most recent 300 events for the task to avoid cross-job event bloat.
                    if target_task_id:
                        task_ids = await session.execute(
                            select(JobEventModel.id)
                            .where(JobEventModel.task_id == target_task_id)
                            .order_by(JobEventModel.id.desc())
                            .offset(300)
                        )
                        old_task_ids = [row[0] for row in task_ids.all()]
                        if old_task_ids:
                            await session.execute(delete(JobEventModel).where(JobEventModel.id.in_(old_task_ids)))

                    await session.commit()
            except Exception as exc:
                if lease_token is not None:
                    raise
                logger.warning(f"Failed to persist job event {event_type}: {exc}")
        message = self._format_sse_message(event_type, normalized_data, event_id, event_created_at)

        dead_queues = []
        for queue, filter_task_id in list(self._subscribers.items()):
            # If subscriber filtered by task_id, only send matching events
            if filter_task_id and filter_task_id != target_task_id:
                continue

            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        for q in dead_queues:
            self.unsubscribe(q)

    async def event_generator(
        self,
        queue: asyncio.Queue,
        task_id: str | None = None,
        replay_messages: list[str] | None = None,
        request: Request | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE messages to HTTP client"""
        try:
            # Send initial replay messages with backpressure & disconnect check
            for replay_message in replay_messages or []:
                if request and await request.is_disconnected():
                    return
                yield replay_message
                await asyncio.sleep(0)

            if request and await request.is_disconnected():
                return
            yield f": keepalive {datetime.now(UTC).isoformat()}\n\n"

            while True:
                if request and await request.is_disconnected():
                    return
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if request and await request.is_disconnected():
                        return
                    yield message
                except TimeoutError:
                    if request and await request.is_disconnected():
                        return
                    yield f": keepalive {datetime.now(UTC).isoformat()}\n\n"
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError, GeneratorExit):
            pass
        finally:
            self.unsubscribe(queue)


event_broadcaster = EventBroadcaster()
