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

    async def list_tasks(
        self,
        project_id: str | None = None,
        *,
        editorial_status: str | None = None,
        production_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TaskModel]:
        statement = select(TaskModel)
        if project_id:
            statement = statement.where(TaskModel.project_id == project_id)
        if editorial_status:
            statement = statement.where(TaskModel.editorial_status == editorial_status)
        if production_status:
            statement = statement.where(TaskModel.production_status == production_status)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(TaskModel.created_at.desc()).offset(offset).limit(limit)
                )
            )
            .unique()
            .all()
        )

    async def delete_task(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        await self.session.delete(task)
        await self.session.commit()
        return True

    async def duplicate_task(self, task_id: str) -> TaskModel:
        source = await self.get_task(task_id)
        detail = source.knowledge_detail or source.commerce_detail or source.drama_episode
        detail_type = source.project.mode
        values = {
            column.name: getattr(detail, column.name)
            for column in detail.__table__.columns
            if column.name not in {"id", "task_id", "project_id", "created_at", "updated_at"}
        }
        values["type"] = detail_type
        values["review_status"] = "draft"
        return await self.create_task(
            source.project_id,
            TaskCreate.model_validate(
                {
                    "title": f"{source.title}（副本）",
                    "description": source.description,
                    "detail": values,
                    "generation_settings": dict(source.generation_settings),
                    "publishing_settings": dict(source.publishing_settings),
                }
            ),
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
        was_approved = task.editorial_status == "approved"
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
        if was_approved and data.model_fields_set:
            task.editorial_status = "draft"
            (task.knowledge_detail or task.commerce_detail or task.drama_episode).review_status = "draft"
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
