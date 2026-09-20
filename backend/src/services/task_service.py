from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundException, ValidationException
from src.models.project import ProjectModel
from src.models.task import TaskModel
from src.models.task_detail import (
    CommerceTaskDetailModel,
    DramaTaskEpisodeModel,
    KnowledgeTaskDetailModel,
)
from src.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_task(self, project_id: str, data: TaskCreate) -> TaskModel:
        project = await self.session.get(ProjectModel, project_id)
        if project is None:
            raise NotFoundException("Project", project_id)
        if data.detail.type != project.mode:
            raise ValidationException(
                f"{project.mode} Project 不能创建 {data.detail.type} Task Detail。"
            )
        task = TaskModel(
            id=f"task_{uuid4().hex[:12]}",
            project_id=project_id,
            title=data.title,
            description=data.description,
            generation_settings=data.generation_settings,
            publishing_settings=data.publishing_settings,
        )
        self.session.add(task)
        await self.session.flush()
        task_detail = self._make_detail(project, task.id, data.detail)
        setattr(
            task,
            {
                "knowledge": "knowledge_detail",
                "commerce": "commerce_detail",
                "drama": "drama_episode",
            }[project.mode],
            task_detail,
        )
        await self.session.commit()
        return await self.get_task(task.id)

    async def list_tasks(self, project_id: str) -> list[TaskModel]:
        return list(
            (
                await self.session.scalars(
                    select(TaskModel)
                    .where(TaskModel.project_id == project_id)
                    .order_by(TaskModel.created_at.desc())
                )
            )
            .unique()
            .all()
        )

    async def get_task(self, task_id: str) -> TaskModel:
        task = await self.session.scalar(
            select(TaskModel)
            .where(TaskModel.id == task_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(TaskModel.project),
                selectinload(TaskModel.knowledge_detail),
                selectinload(TaskModel.commerce_detail),
                selectinload(TaskModel.drama_episode),
                selectinload(TaskModel.scenes),
            )
        )
        if task is None:
            raise NotFoundException("Task", task_id)
        return task

    async def update_task(self, task_id: str, data: TaskUpdate) -> TaskModel:
        task = await self.get_task(task_id)
        project = await self.session.get(ProjectModel, task.project_id)
        values = data.model_dump(exclude_unset=True, exclude={"detail"})
        for key, value in values.items():
            setattr(task, key, value)
        if data.detail is not None:
            if data.detail.type != project.mode:
                raise ValidationException("Task Detail 与 Project 模式不匹配。")
            current = {
                "knowledge": task.knowledge_detail,
                "commerce": task.commerce_detail,
                "drama": task.drama_episode,
            }[project.mode]
            for key, value in data.detail.model_dump(exclude={"type"}).items():
                setattr(current, key, value)
        await self.session.commit()
        return await self.get_task(task_id)

    async def approve(self, task_id: str) -> TaskModel:
        task = await self.get_task(task_id)
        task.editorial_status = "approved"
        detail = task.knowledge_detail or task.commerce_detail or task.drama_episode
        detail.review_status = "approved"
        await self.session.commit()
        return task

    @staticmethod
    def _make_detail(project, task_id, detail):
        values = detail.model_dump(exclude={"type"})
        if project.mode == "knowledge":
            return KnowledgeTaskDetailModel(task_id=task_id, **values)
        if project.mode == "commerce":
            return CommerceTaskDetailModel(task_id=task_id, **values)
        return DramaTaskEpisodeModel(task_id=task_id, project_id=project.id, **values)
