from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.models.scene import SceneModel
from src.models.task import TaskModel
from src.models.workflow import WorkflowJobModel
from src.services.production_context import ProductionContextCompiler
from src.services.provider_manager import ProviderManager
from src.services.workflow_runtime import sha256_file
from src.services.workflow_service import workflow_service


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


class ProductionJobService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, task_id: str) -> WorkflowJobModel:
        task = await self.session.get(TaskModel, task_id)
        if task is None:
            raise NotFoundException("Task", task_id)
        if task.editorial_status != "approved":
            raise ValidationException("Task 必须先通过审核才能生产。")
        compiler = ProductionContextCompiler(self.session)
        readiness = await compiler.readiness(task_id)
        if not readiness["ready"]:
            messages = [item["message"] for item in readiness["checks"] if item["status"] == "error"]
            raise ValidationException("生产准备未完成：" + "；".join(messages))
        active = await self.session.scalar(
            select(WorkflowJobModel.id).where(
                WorkflowJobModel.task_id == task_id,
                WorkflowJobModel.job_type == "full_pipeline",
                WorkflowJobModel.status.in_(["queued", "running", "retrying"]),
            )
        )
        if active:
            raise ValidationException("Task 已有未完成的 WorkflowJob。")
        providers = await ProviderManager(self.session).capture_snapshot()
        workflow_config = {
            key: value
            for key, value in task.generation_settings.items()
            if key.endswith("_workflow_id") or key.endswith("_workflow_snapshot")
        }
        for kind in ("image", "video"):
            workflow_id = task.generation_settings.get(f"{kind}_workflow_id")
            if not workflow_id:
                continue
            path = workflow_service.resolve_workflow_file(workflow_id)
            if path is None or not path.is_file():
                raise ValidationException(f"显式选择的 {kind} workflow 不存在：{workflow_id}")
            workflow_config[f"{kind}_workflow_snapshot"] = {
                "id": workflow_id,
                "path": str(path),
                "sha256": await sha256_file(path),
            }
        snapshot = await compiler.compile(
            task_id, provider_snapshot=providers, workflow_config=workflow_config
        )
        job = WorkflowJobModel(
            id=f"job_{uuid4().hex[:12]}",
            task_id=task_id,
            production_context_snapshot_id=snapshot.id,
            job_type="full_pipeline",
            status="queued",
            current_stage="queued",
            progress=0,
            params={},
            checkpoint={},
            retry_count=0,
            max_retries=3,
            available_at=_now(),
        )
        self.session.add(job)
        task.production_status = "queued"
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def retry(self, job_id: str) -> WorkflowJobModel:
        source = await self.session.get(WorkflowJobModel, job_id)
        if source is None:
            raise NotFoundException("WorkflowJob", job_id)
        if source.job_type != "full_pipeline":
            raise ValidationException("该 WorkflowJob 不是生产 Job。")
        if source.status not in {"failed", "cancelled"}:
            raise ValidationException("只有失败或取消的 WorkflowJob 可以重试。")
        retry = WorkflowJobModel(
            id=f"job_{uuid4().hex[:12]}",
            task_id=source.task_id,
            production_context_snapshot_id=source.production_context_snapshot_id,
            job_type=source.job_type,
            status="queued",
            current_stage="queued",
            progress=0,
            params={**(source.params or {}), "retry_of_job_id": source.id},
            checkpoint=dict(source.checkpoint or {}),
            retry_count=source.retry_count + 1,
            max_retries=source.max_retries,
            available_at=_now(),
        )
        self.session.add(retry)
        task = await self.session.get(TaskModel, source.task_id)
        task.production_status = "queued"
        await self.session.commit()
        await self.session.refresh(retry)
        return retry

    async def retry_scene(self, task_id: str, scene_id: str) -> WorkflowJobModel:
        scene = await self.session.get(SceneModel, scene_id)
        if scene is None or scene.task_id != task_id:
            raise NotFoundException("Scene", scene_id)
        active = await self.session.scalar(
            select(WorkflowJobModel.id).where(
                WorkflowJobModel.task_id == task_id,
                WorkflowJobModel.status.in_(["queued", "running", "retrying"]),
            )
        )
        if active:
            raise ValidationException("Task 已有未完成的 WorkflowJob。")
        source = await self.session.scalar(
            select(WorkflowJobModel)
            .where(
                WorkflowJobModel.task_id == task_id,
                WorkflowJobModel.production_context_snapshot_id.is_not(None),
            )
            .order_by(WorkflowJobModel.created_at.desc())
            .limit(1)
        )
        if source is None:
            raise ValidationException("请先创建一次完整生产 Job，才能按原快照重试单镜。")
        retry = WorkflowJobModel(
            id=f"job_{uuid4().hex[:12]}",
            task_id=task_id,
            production_context_snapshot_id=source.production_context_snapshot_id,
            job_type="full_pipeline",
            status="queued",
            current_stage="queued",
            progress=0,
            params={
                "retry_of_job_id": source.id,
                "single_step": "assets",
                "single_unit": scene_id,
                "force_unit": scene_id,
            },
            checkpoint={},
            retry_count=source.retry_count + 1,
            max_retries=source.max_retries,
            available_at=_now(),
        )
        self.session.add(retry)
        task = await self.session.get(TaskModel, task_id)
        task.production_status = "queued"
        await self.session.commit()
        await self.session.refresh(retry)
        return retry
