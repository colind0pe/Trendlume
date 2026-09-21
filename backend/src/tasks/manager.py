import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.exceptions import ValidationException
from src.core.security import redact_sensitive_text
from src.domain.enums import JobStatus, JobType, PublishJobStatus
from src.models.publishing import PublishingJobModel
from src.models.workflow import WorkflowJobModel
from src.services.workflow_execution import (
    WorkflowExecutionContext,
    WorkflowLeaseLost,
    interrupt_steps,
    lock_task,
)
from src.services.workflow_runtime import redact
from src.tasks.broadcaster import event_broadcaster
from src.tasks.executor import VideoWorkflowExecutor, workflow_executor
from src.tasks.job import Job


def _now() -> datetime:
    """Use naive UTC values because SQLite DateTime columns are timezone-naive."""
    return datetime.now(UTC).replace(tzinfo=None)


TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
    JobStatus.MISSED.value,
    JobStatus.UNCERTAIN.value,
}


class TaskManager:
    """SQLite-backed single-host queue with resumable jobs and a polling scheduler."""

    def __init__(self, num_workers: int = settings.max_concurrent_workers, session_factory=None, executor: VideoWorkflowExecutor | None = None):
        self.num_workers = num_workers
        self.session_factory = session_factory or async_session_factory
        self.executor = executor or workflow_executor
        # The queue only wakes workers; durable state lives in SQLite.
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.workers: list[asyncio.Task] = []
        self.poller: asyncio.Task | None = None
        self._running = False
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._task_to_job: dict[str, str] = {}
        self._enqueued_job_ids: set[str] = set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._recover_stale_jobs()
        self.poller = asyncio.create_task(self._poll_loop(), name="TaskManager-Poller")
        for i in range(self.num_workers):
            self.workers.append(asyncio.create_task(self._worker_loop(i), name=f"TaskManager-Worker-{i}"))
        logger.info(f"TaskManager started with {self.num_workers} workers (SQLite durable queue).")

    async def stop(self) -> None:
        self._running = False
        tasks = [task for task in self.workers if not task.done()]
        if self.poller and not self.poller.done():
            self.poller.cancel()
            tasks.append(self.poller)
        for worker in self.workers:
            if not worker.done():
                worker.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.workers.clear()
        self.poller = None
        self._active_tasks.clear()
        self._enqueued_job_ids.clear()
        logger.info("TaskManager stopped.")

    async def _recover_stale_jobs(self) -> None:
        now = _now()
        stale_before = now - timedelta(seconds=settings.job_stale_after_seconds)
        try:
            async with self.session_factory() as session:
                stale = await session.execute(select(WorkflowJobModel).where(
                    WorkflowJobModel.status == JobStatus.RUNNING.value,
                    or_(WorkflowJobModel.heartbeat_at.is_(None), WorkflowJobModel.heartbeat_at < stale_before),
                ))
                for job in stale.scalars().all():
                    await self._expire_lease(session, job, stale_before, "服务重启后从上次完成阶段恢复")

                overdue = await session.execute(select(WorkflowJobModel).where(
                    WorkflowJobModel.job_type == JobType.PUBLISH.value,
                    WorkflowJobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RETRYING.value]),
                    WorkflowJobModel.scheduled_at.is_not(None),
                    WorkflowJobModel.scheduled_at < now - timedelta(seconds=settings.schedule_misfire_grace_seconds),
                ))
                for job in overdue.scalars().all():
                    job.status = JobStatus.MISSED.value
                    job.error_message = "服务停机期间错过发布时间，请确认后重新发布"
                    pub_id = (job.params or {}).get("publishing_job_id")
                    if pub_id:
                        pub = await session.get(PublishingJobModel, pub_id)
                        if pub:
                            pub.status = PublishJobStatus.MISSED.value
                            pub.error_message = job.error_message
                await session.commit()
        except Exception as exc:
            logger.exception(f"Error recovering durable jobs: {exc}")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._requeue_stale_running_jobs()
                await self._mark_missed_scheduled_jobs()
                async with self.session_factory() as session:
                    result = await session.execute(select(WorkflowJobModel).where(
                        WorkflowJobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RETRYING.value]),
                        WorkflowJobModel.available_at <= _now(),
                    ).order_by(WorkflowJobModel.available_at, WorkflowJobModel.created_at).limit(self.num_workers * 2))
                    models = list(result.scalars().all())
                for model in models:
                    await self._enqueue_model(model)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Durable queue poll failed: {redact_sensitive_text(str(exc))}")
            await asyncio.sleep(settings.job_poll_interval_seconds)

    async def _requeue_stale_running_jobs(self) -> None:
        cutoff = _now() - timedelta(seconds=settings.job_stale_after_seconds)
        async with self.session_factory() as session:
            result = await session.execute(
                select(WorkflowJobModel).where(
                    WorkflowJobModel.status == JobStatus.RUNNING.value,
                    or_(WorkflowJobModel.heartbeat_at.is_(None), WorkflowJobModel.heartbeat_at < cutoff),
                )
            )
            changed = False
            for model in result.scalars().all():
                changed = await self._expire_lease(session, model, cutoff, "Worker 心跳超时，从上次完成阶段恢复") or changed

            if changed:
                await session.commit()

    async def _expire_lease(self, session, model, cutoff, reason) -> bool:
        with session.no_autoflush:
            result = await session.execute(update(WorkflowJobModel).where(
                WorkflowJobModel.id == model.id,
                WorkflowJobModel.lease_token == model.lease_token,
                WorkflowJobModel.status == JobStatus.RUNNING.value,
                or_(WorkflowJobModel.heartbeat_at.is_(None), WorkflowJobModel.heartbeat_at < cutoff),
            ).values(status=JobStatus.QUEUED.value, available_at=_now(), heartbeat_at=None,
                     lease_token=None, error_message=reason)
              .execution_options(synchronize_session=False, autoflush=False))
        if result.rowcount != 1:
            return False
        await interrupt_steps(session, model.id)
        return True

    async def _mark_missed_scheduled_jobs(self) -> None:
        """Prevent a busy worker pool from silently publishing far past its schedule."""
        cutoff = _now() - timedelta(seconds=settings.schedule_misfire_grace_seconds)
        async with self.session_factory() as session:
            result = await session.execute(
                select(WorkflowJobModel).where(
                    WorkflowJobModel.job_type == JobType.PUBLISH.value,
                    WorkflowJobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RETRYING.value]),
                    WorkflowJobModel.scheduled_at.is_not(None),
                    WorkflowJobModel.scheduled_at < cutoff,
                )
            )
            changed = False
            for model in result.scalars().all():
                model.status = JobStatus.MISSED.value
                model.error_message = "已超过计划发布时间宽限期，请确认后重新发布"
                model.completed_at = _now()
                pub_id = (model.params or {}).get("publishing_job_id")
                if pub_id:
                    pub = await session.get(PublishingJobModel, pub_id)
                    if pub:
                        pub.status = PublishJobStatus.MISSED.value
                        pub.error_message = model.error_message
                changed = True
            if changed:
                await session.commit()

    async def _enqueue_model(self, model: WorkflowJobModel, event_session_factory=None) -> None:
        if model.id in self._enqueued_job_ids:
            return
        self._enqueued_job_ids.add(model.id)
        job = self._model_to_job(model)
        event_broadcaster.bind_job(job.task_id, job.id, event_session_factory or self.session_factory)
        self._task_to_job[job.task_id] = job.id
        await self.queue.put(job)

    @staticmethod
    def _model_to_job(model: WorkflowJobModel) -> Job:
        try:
            status = JobStatus(model.status)
        except ValueError:
            status = JobStatus.PENDING
        def aware(value):
            return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value
        return Job(id=model.id, task_id=model.task_id, job_type=model.job_type, status=status, progress=model.progress,
                   current_stage=model.current_stage, error_message=model.error_message, retry_count=model.retry_count,
                   lease_token=model.lease_token,
                   max_retries=model.max_retries, params=dict(model.params or {}), result=model.result,
                   created_at=aware(model.created_at), started_at=aware(model.started_at),
                   heartbeat_at=aware(model.heartbeat_at), completed_at=aware(model.completed_at),
                   available_at=aware(model.available_at), scheduled_at=aware(model.scheduled_at),
                   updated_at=aware(model.updated_at),
                   checkpoint=dict(model.checkpoint or {}))

    async def submit_task(self, task_id: str, job_type: str, params: dict[str, Any] | None = None,
                          available_at: datetime | None = None, scheduled_at: datetime | None = None,
                          checkpoint: dict[str, Any] | None = None,
                          retry_count: int = 0, session_factory=None) -> Job:
        # Queue metadata is user-visible and durable; never persist provider
        # credentials or URL userinfo accidentally supplied by a caller.
        params = redact(params or {})
        checkpoint = redact(checkpoint or {})
        now = _now()
        factory = session_factory or self.session_factory
        if job_type != JobType.PUBLISH.value:
            raise ValidationException(
                "生产 Job 必须通过 ProductionJobService 创建；TaskManager 仅调度发布。"
            )
        available = available_at or now
        if available.tzinfo:
            available = available.astimezone(UTC).replace(tzinfo=None)
        if scheduled_at and scheduled_at.tzinfo:
            scheduled_at = scheduled_at.astimezone(UTC).replace(tzinfo=None)
        async with factory() as session:
            await lock_task(session, task_id)
            existing_res = await session.execute(select(WorkflowJobModel).where(
                WorkflowJobModel.task_id == task_id,
                ~WorkflowJobModel.status.in_(list(TERMINAL_JOB_STATUSES)),
            ).order_by(WorkflowJobModel.created_at.desc()).limit(1))
            existing = existing_res.scalar_one_or_none()
            if existing:
                if existing.job_type != job_type:
                    raise ValidationException(
                        f"任务已有未完成的 {existing.job_type} Job，完成或取消后才能提交 {job_type}。"
                    )
                job = self._model_to_job(existing)
                self._task_to_job[task_id] = job.id
                event_broadcaster.bind_job(task_id, job.id, self.session_factory)
                if existing.status in {JobStatus.QUEUED.value, JobStatus.RETRYING.value} and available <= now:
                    await self._enqueue_model(existing, event_session_factory=factory)
                return job

            production_context_snapshot_id = await session.scalar(
                select(WorkflowJobModel.production_context_snapshot_id)
                .where(
                    WorkflowJobModel.task_id == task_id,
                    WorkflowJobModel.job_type == JobType.FULL_PIPELINE.value,
                    WorkflowJobModel.status == JobStatus.COMPLETED.value,
                )
                .order_by(WorkflowJobModel.created_at.desc())
                .limit(1)
            )
            if not production_context_snapshot_id:
                raise ValidationException("只有成功生产 Job 的最终视频可以进入发布队列。")
            model = WorkflowJobModel(id=f"job_{uuid.uuid4().hex[:12]}", task_id=task_id, job_type=job_type,
                                     production_context_snapshot_id=production_context_snapshot_id,
                                     status=JobStatus.QUEUED.value, current_stage="queued", progress=0,
                                     params=params or {}, checkpoint=checkpoint or {}, retry_count=retry_count,
                                     max_retries=settings.max_job_retries, available_at=available,
                                     scheduled_at=scheduled_at, created_at=now, updated_at=now)
            session.add(model)
            await session.commit()
            job = self._model_to_job(model)
        self._task_to_job[task_id] = job.id
        event_broadcaster.bind_job(task_id, job.id, self.session_factory)
        if available <= now:
            await self._enqueue_model(model, event_session_factory=factory)
        await event_broadcaster.broadcast("step.started", {
            "task_id": task_id, "job_id": job.id, "stage": "queued", "status": JobStatus.QUEUED.value,
            "progress": 0, "message": f"任务已持久化排队 ({job_type})",
        }, task_id=task_id, job_id=job.id)
        return job

    async def _claim_job(self, job_id: str) -> WorkflowJobModel | None:
        # SQLite can report SQLITE_LOCKED (rather than SQLITE_BUSY) when the
        # poller and a worker touch the queue at the same instant. A failed
        # claim is harmless; retry the conditional claim before the worker
        # treats it as a job failure.
        for attempt in range(8):
            try:
                async with self.session_factory() as session:
                    now = _now()
                    result = await session.execute(
                        update(WorkflowJobModel)
                        .where(
                            WorkflowJobModel.id == job_id,
                            WorkflowJobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RETRYING.value]),
                            WorkflowJobModel.available_at <= now,
                        )
                        .values(
                            status=JobStatus.RUNNING.value,
                            started_at=WorkflowJobModel.started_at,
                            heartbeat_at=now,
                            lease_token=uuid.uuid4().hex,
                            updated_at=now,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    if result.rowcount != 1:
                        return None
                    model = await session.get(WorkflowJobModel, job_id)
                    if model:
                        await session.refresh(model)
                    if model and model.started_at is None:
                        model.started_at = now
                    await session.commit()
                    return model
            except OperationalError as exc:
                if 'locked' not in str(exc).lower() or attempt == 7:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))
        return None

    async def run_inline(self, task_id: str, params: dict[str, Any], session_factory=None) -> dict[str, Any]:
        """Run one durable workflow operation under an exclusive lease."""
        from sqlalchemy.ext.asyncio import async_sessionmaker
        factory = session_factory or self.session_factory
        async with factory() as session:
            await assert_task_editable(session, task_id)
            now = _now()
            model = WorkflowJobModel(id=f"job_{uuid.uuid4().hex[:12]}", task_id=task_id,
                job_type=JobType.FULL_PIPELINE.value, status=JobStatus.RUNNING.value,
                current_stage=params.get("single_step", "queued"), params=params,
                lease_token=uuid.uuid4().hex, started_at=now, heartbeat_at=now,
                available_at=now, max_retries=0)
            session.add(model)
            await session.commit()
            job = self._model_to_job(model)
            heartbeat_factory = async_sessionmaker(session.bind, expire_on_commit=False, autoflush=False)
        owner = TaskManager(session_factory=factory)
        heartbeat_owner = TaskManager(session_factory=heartbeat_factory)
        heartbeat_owner._running = True
        event_broadcaster.bind_job(task_id, job.id, factory)
        self._active_tasks[task_id] = asyncio.current_task()
        pulse = asyncio.create_task(heartbeat_owner._heartbeat_loop(job.id, job.lease_token))
        try:
            result = await VideoWorkflowExecutor(session_factory=factory).execute(job)
            await owner._finish_job(job.id, result, lease_token=job.lease_token)
            await event_broadcaster.broadcast("job.completed", {
                "task_id": task_id, "job_id": job.id, "status": "completed", "result": result,
            }, task_id=task_id, job_id=job.id)
            return result
        except WorkflowLeaseLost:
            raise
        except asyncio.CancelledError:
            try:
                await owner._requeue_interrupted(job.id, lease_token=job.lease_token)
            except WorkflowLeaseLost:
                pass
            raise
        except Exception as exc:
            await owner._fail_or_retry(job.id, redact_sensitive_text(str(exc)), lease_token=job.lease_token)
            raise
        finally:
            heartbeat_owner._running = False
            pulse.cancel()
            await asyncio.gather(pulse, return_exceptions=True)
            if self._active_tasks.get(task_id) is asyncio.current_task():
                self._active_tasks.pop(task_id, None)

    async def heartbeat(self, job_id: str, current_stage: str | None = None, progress: int | None = None, *, lease_token: str | None = None) -> None:
        async with self.session_factory() as session:
            await WorkflowExecutionContext(job_id, lease_token or "").fence(session)
            model = await session.get(WorkflowJobModel, job_id)
            if model and model.status == JobStatus.RUNNING.value:
                model.heartbeat_at = _now()
                if current_stage:
                    model.current_stage = current_stage
                if progress is not None:
                    model.progress = progress
                await session.commit()

    async def _heartbeat_loop(self, job_id: str, lease_token: str) -> None:
        while self._running:
            await asyncio.sleep(settings.job_heartbeat_interval_seconds)
            try:
                await self.heartbeat(job_id, lease_token=lease_token)
            except OperationalError as exc:
                logger.warning(f"Heartbeat write failed for job {job_id}; will retry: {exc}")

    async def _finish_job(self, job_id: str, result: dict[str, Any] | None = None, *, lease_token: str | None = None) -> None:
        async with self.session_factory() as session:
            await WorkflowExecutionContext(job_id, lease_token or "").fence(session)
            model = await session.get(WorkflowJobModel, job_id)
            if model:
                model.status = JobStatus.COMPLETED.value
                model.current_stage = "completed"
                model.progress = 100
                model.result = result
                model.completed_at = _now()
                model.heartbeat_at = None
                model.lease_token = None
                await interrupt_steps(session, model.id, "interrupted")
                await session.commit()

    async def _fail_or_retry(self, job_id: str, error: str, *, lease_token: str | None = None) -> None:
        async with self.session_factory() as session:
            await WorkflowExecutionContext(job_id, lease_token or "").fence(session)
            model = await session.get(WorkflowJobModel, job_id)
            if not model or model.status == JobStatus.CANCELLED.value:
                return
            pub = None
            if model.job_type == JobType.PUBLISH.value and (model.params or {}).get("publishing_job_id"):
                pub = await session.get(PublishingJobModel, model.params["publishing_job_id"])
            if pub and pub.status == PublishJobStatus.UNCERTAIN.value:
                model.status = JobStatus.UNCERTAIN.value
                model.error_message = error
                model.completed_at = _now()
                model.heartbeat_at = None
                model.lease_token = None
                await interrupt_steps(session, model.id, "interrupted")
                await session.commit()
                return
            if model.job_type == JobType.PUBLISH.value and model.retry_count < model.max_retries:
                delay = (30, 120, 300)[min(model.retry_count, 2)]
                model.retry_count += 1
                model.status = JobStatus.RETRYING.value
                model.available_at = _now() + timedelta(seconds=delay)
                model.error_message = error
                model.heartbeat_at = None
                model.lease_token = None
                await interrupt_steps(session, model.id, "interrupted")
            else:
                model.status = JobStatus.FAILED.value
                model.error_message = error
                model.completed_at = _now()
                model.heartbeat_at = None
                model.lease_token = None
                await interrupt_steps(session, model.id, "interrupted")
            await session.commit()

    async def _requeue_interrupted(self, job_id: str, force_resume: bool = False, *, lease_token: str | None = None) -> None:
        async with self.session_factory() as session:
            await WorkflowExecutionContext(job_id, lease_token or "").fence(session)
            model = await session.get(WorkflowJobModel, job_id)
            if model and model.status == JobStatus.RUNNING.value:
                model.status = JobStatus.QUEUED.value
                model.available_at = _now()
                model.heartbeat_at = None
                model.lease_token = None
                await interrupt_steps(session, model.id, "interrupted")
                model.error_message = "Worker 停止，任务将在下次启动时从检查点恢复"
                await session.commit()

    async def _mark_job_uncertain(self, job_id: str, error: str, *, lease_token: str | None = None) -> None:
        async with self.session_factory() as session:
            await WorkflowExecutionContext(job_id, lease_token or "").fence(session)
            model = await session.get(WorkflowJobModel, job_id)
            if model:
                model.status = JobStatus.UNCERTAIN.value
                model.error_message = error
                model.completed_at = _now()
                model.heartbeat_at = None
                model.lease_token = None
                await interrupt_steps(session, model.id, "interrupted")
                await session.commit()

    async def get_job(self, job_id: str, session_factory=None) -> WorkflowJobModel | None:
        async with (session_factory or self.session_factory)() as session:
            return await session.get(WorkflowJobModel, job_id)

    async def get_latest_job(self, task_id: str, job_type: str | None = None, session_factory=None, exclude_publish: bool = False) -> WorkflowJobModel | None:
        async with (session_factory or self.session_factory)() as session:
            filters = [WorkflowJobModel.task_id == task_id]
            if exclude_publish:
                filters.append(WorkflowJobModel.job_type != JobType.PUBLISH.value)
            if job_type:
                filters.append(WorkflowJobModel.job_type == job_type)
            result = await session.execute(select(WorkflowJobModel).where(*filters).order_by(WorkflowJobModel.created_at.desc()).limit(1))
            return result.scalar_one_or_none()

    async def list_jobs(self, task_id: str, session_factory=None) -> list[WorkflowJobModel]:
        async with (session_factory or self.session_factory)() as session:
            result = await session.execute(select(WorkflowJobModel).where(WorkflowJobModel.task_id == task_id).order_by(WorkflowJobModel.created_at.desc()))
            return list(result.scalars().all())

    async def _find_publishing_workflows(self, session, publishing_job_id: str) -> list[WorkflowJobModel]:
        result = await session.execute(
            select(WorkflowJobModel).where(WorkflowJobModel.job_type == JobType.PUBLISH.value)
        )
        return [
            model
            for model in result.scalars().all()
            if (model.params or {}).get("publishing_job_id") == publishing_job_id
        ]

    async def confirm_missed_publish(self, publishing_job_id: str, session_factory=None) -> Job:
        async with (session_factory or self.session_factory)() as session:
            workflows = await self._find_publishing_workflows(session, publishing_job_id)
            model = workflows[0] if workflows else None
            if not model or model.status != JobStatus.MISSED.value:
                raise ValueError("该发布任务不存在或不处于待确认状态")
            model.status = JobStatus.QUEUED.value
            model.available_at = _now()
            model.scheduled_at = None
            model.error_message = None
            pub = await session.get(PublishingJobModel, publishing_job_id)
            if pub:
                pub.status = PublishJobStatus.QUEUED.value
                pub.error_message = None
            await session.commit()
        await self._enqueue_model(model, event_session_factory=session_factory or self.session_factory)
        return self._model_to_job(model)

    async def cancel_publishing_workflow(self, publishing_job_id: str, session_factory=None) -> bool:
        async with (session_factory or self.session_factory)() as session:
            pub = await session.get(PublishingJobModel, publishing_job_id)
            if not pub:
                return False
            if pub.status == PublishJobStatus.PUBLISHED.value:
                raise ValidationException("已发布的作品不能取消发布。")
            linked_jobs = await self._find_publishing_workflows(session, publishing_job_id)
            model = max(linked_jobs, key=lambda item: item.created_at) if linked_jobs else None
            if not model:
                pub.status = PublishJobStatus.CANCELLED.value
                pub.error_message = "用户取消发布"
                await session.commit()
                return True
            for linked in linked_jobs:
                linked.status = JobStatus.CANCELLED.value
                linked.completed_at = _now()
                linked.heartbeat_at = None
            model.status = JobStatus.CANCELLED.value
            model.completed_at = _now()
            pub = await session.get(PublishingJobModel, publishing_job_id)
            if pub:
                pub.status = PublishJobStatus.CANCELLED.value
                pub.error_message = "用户取消发布"
            await session.commit()
            running = self._active_tasks.get(model.task_id) if self._task_to_job.get(model.task_id) in {item.id for item in linked_jobs} else None
        if running and not running.done():
            running.cancel()
        await event_broadcaster.broadcast(
            "job.cancelled",
            {
                "task_id": model.task_id,
                "job_id": model.id,
                "stage": "publishing",
                "status": JobStatus.CANCELLED.value,
                "progress": model.progress,
                "message": "发布 Job 已被取消。",
            },
            task_id=model.task_id,
            job_id=model.id,
        )
        return True

    async def resolve_uncertain_publish(self, publishing_job_id: str, action: str, session_factory=None) -> Job | None:
        async with (session_factory or self.session_factory)() as session:
            workflows = await self._find_publishing_workflows(session, publishing_job_id)
            model = workflows[0] if workflows else None
            if not model or model.status != JobStatus.UNCERTAIN.value:
                raise ValueError("该发布任务不存在或不处于结果不确定状态")
            pub = await session.get(PublishingJobModel, publishing_job_id)
            if action == "acknowledge":
                model.status = JobStatus.COMPLETED.value
                model.completed_at = _now()
                if pub:
                    pub.status = PublishJobStatus.PUBLISHED.value
                    pub.error_message = "用户确认平台已完成发布"
            elif action == "retry":
                model.status = JobStatus.QUEUED.value
                model.available_at = _now()
                model.error_message = None
                if pub:
                    pub.status = PublishJobStatus.QUEUED.value
                    pub.error_message = None
            else:
                raise ValueError("action 必须为 retry 或 acknowledge")
            await session.commit()
        if action == "retry":
            await self._enqueue_model(model, event_session_factory=session_factory or self.session_factory)
        return self._model_to_job(model)

    async def _worker_loop(self, worker_id: int) -> None:
        logger.debug(f"Worker-{worker_id} ready.")
        while self._running:
            try:
                job = await self.queue.get()
            except asyncio.CancelledError:
                break
            self._enqueued_job_ids.discard(job.id)
            claimed = None
            heartbeat_task: asyncio.Task | None = None
            try:
                claimed = await self._claim_job(job.id)
                if not claimed:
                    continue
                # Requests may pass a short-lived session factory for API/test
                # isolation. Once a worker owns the job, bind event persistence
                # to the manager's long-lived application factory instead.
                event_broadcaster.bind_job(job.task_id, job.id, self.session_factory)
                self._active_tasks[job.task_id] = asyncio.current_task()  # type: ignore[assignment]
                job.status = JobStatus.RUNNING
                job.lease_token = claimed.lease_token
                await event_broadcaster.broadcast(
                    "job.started",
                    {
                        "task_id": job.task_id,
                        "job_id": job.id,
                        "stage": claimed.current_stage or "queued",
                        "status": JobStatus.RUNNING.value,
                        "progress": claimed.progress,
                        "message": "任务已由 Worker 接管，开始执行。",
                    },
                    task_id=job.task_id,
                    job_id=job.id,
                )
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(job.id, claimed.lease_token), name=f"Heartbeat-{job.id}")
                job_result: dict[str, Any] | None = None
                if job.job_type == JobType.PUBLISH.value:
                    from src.services.publishing_service import PublishingService
                    published = None
                    async with self.session_factory() as session:
                        pub_job_id = job.params.get("publishing_job_id")
                        if pub_job_id:
                            published = await PublishingService(session).execute_publish_job(pub_job_id)
                            if published.status == PublishJobStatus.UNCERTAIN.value:
                                await self._mark_job_uncertain(job.id, published.error_message or "发布结果未知", lease_token=claimed.lease_token)
                                await event_broadcaster.broadcast(
                                    "job.uncertain",
                                    {"task_id": job.task_id, "job_id": job.id, "status": JobStatus.UNCERTAIN.value,
                                     "message": published.error_message or "发布结果未知"},
                                    task_id=job.task_id, job_id=job.id,
                                )
                                continue
                            if published.status == PublishJobStatus.FAILED.value:
                                raise RuntimeError(published.error_message or "抖音发布失败")
                    job_result = {
                        "publishing_job_id": job.params.get("publishing_job_id"),
                        "status": published.status if published else PublishJobStatus.PUBLISHED.value,
                        "platform_post_id": published.platform_post_id if published else None,
                    }
                    await self._finish_job(
                        job.id,
                        result=job_result, lease_token=claimed.lease_token,
                    )
                else:
                    job_result = await self.executor.execute(job)
                    await self._finish_job(job.id, job_result, lease_token=claimed.lease_token)
                await event_broadcaster.broadcast(
                    "job.completed",
                    {
                        "task_id": job.task_id,
                        "job_id": job.id,
                        "stage": "completed",
                        "status": JobStatus.COMPLETED.value,
                        "progress": 100,
                        "message": "Job 执行完成。",
                        "result": job_result,
                    },
                    task_id=job.task_id,
                    job_id=job.id,
                )
            except WorkflowLeaseLost:
                continue
            except asyncio.CancelledError:
                if claimed:
                    try:
                        await self._requeue_interrupted(job.id, force_resume=not self._running, lease_token=claimed.lease_token)
                    except WorkflowLeaseLost:
                        pass
                if self._running:
                    # User cancellation should free this worker for the next job;
                    # shutdown cancellation exits the loop below.
                    continue
                raise
            except Exception as exc:
                safe_error = redact_sensitive_text(str(exc))
                logger.error(f"Worker-{worker_id}: Job {job.id} failed: {safe_error}")
                try:
                    await self._fail_or_retry(job.id, safe_error, lease_token=claimed.lease_token if claimed else None)
                except WorkflowLeaseLost:
                    continue
                failed_state = await self.get_job(job.id)
                failed_status = failed_state.status if failed_state else JobStatus.FAILED.value
                await event_broadcaster.broadcast(
                    "job.retrying" if failed_status == JobStatus.RETRYING.value else "job.failed",
                    {
                        "task_id": job.task_id,
                        "job_id": job.id,
                        "stage": failed_state.current_stage if failed_state else job.current_stage,
                        "status": failed_status,
                        "progress": failed_state.progress if failed_state else job.progress,
                        "error": safe_error,
                        "message": safe_error,
                    },
                    task_id=job.task_id, job_id=job.id,
                )
            finally:
                if heartbeat_task and not heartbeat_task.done():
                    heartbeat_task.cancel()
                if self._active_tasks.get(job.task_id) is asyncio.current_task():
                    self._active_tasks.pop(job.task_id, None)
                self.queue.task_done()


task_manager = TaskManager()
