from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.models.project import ProjectModel
from src.models.project_context import (
    CommerceProjectProfileModel,
    DramaProjectProfileModel,
    DramaStyleGuideModel,
    KnowledgeProjectProfileModel,
)
from src.models.template import ProjectTemplateModel
from src.schemas.project import ProjectCreate, ProjectUpdate
from src.services.template_catalog import template_catalog


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_project(self, data: ProjectCreate) -> ProjectModel:
        project = ProjectModel(
            id=f"project_{uuid4().hex[:12]}",
            name=data.name,
            description=data.description,
            mode=data.mode,
            aspect_ratio=data.aspect_ratio,
            default_production_settings=data.default_production_settings,
        )
        self.session.add(project)
        await self.session.flush()
        template_id = template_catalog.get_default_for_aspect(data.aspect_ratio)
        catalog_item = template_catalog.get(template_id, data.aspect_ratio)
        project.template = ProjectTemplateModel(
            id=f"project_template_{uuid4().hex[:12]}",
            project_id=project.id,
            aspect_ratio=data.aspect_ratio,
            template_id=template_id,
            template_version=str((catalog_item or {}).get("version") or "1"),
            frame_template=str(
                (catalog_item or {}).get("html_path") or "1080x1920/default.html"
            ),
        )
        if data.mode == "knowledge":
            project.knowledge_profile = KnowledgeProjectProfileModel(
                project_id=project.id, **data.knowledge_profile.model_dump()
            )
        elif data.mode == "commerce":
            project.commerce_profile = CommerceProjectProfileModel(
                project_id=project.id, **data.commerce_profile.model_dump()
            )
        else:
            project.drama_profile = DramaProjectProfileModel(
                project_id=project.id, **data.drama_profile.model_dump()
            )
            project.drama_style_guide = DramaStyleGuideModel(
                project_id=project.id,
                **(data.drama_style_guide.model_dump() if data.drama_style_guide else {}),
            )
        await self.session.commit()
        return await self.get_project(project.id)

    async def list_projects(self):
        return list(
            (
                await self.session.scalars(
                    select(ProjectModel).order_by(ProjectModel.updated_at.desc())
                )
            )
            .unique()
            .all()
        )

    async def get_project(self, project_id: str):
        project = await self.session.get(ProjectModel, project_id)
        if project is None:
            raise NotFoundException("Project", project_id)
        return project

    async def update_project(self, project_id: str, data: ProjectUpdate):
        project = await self.get_project(project_id)
        values = data.model_dump(
            exclude_unset=True,
            exclude={"knowledge_profile", "commerce_profile", "drama_profile", "drama_style_guide"},
        )
        if "mode" in values:
            raise ValidationException("Project mode 创建后不可修改。")
        for key, value in values.items():
            setattr(project, key, value)
        supplied = {
            "knowledge": data.knowledge_profile,
            "commerce": data.commerce_profile,
            "drama": data.drama_profile,
        }
        if any(value is not None for value in supplied.values()):
            if (
                supplied[project.mode] is None
                or sum(value is not None for value in supplied.values()) != 1
            ):
                raise ValidationException("只能编辑与 Project mode 匹配的 Profile。")
            profile = {
                "knowledge": project.knowledge_profile,
                "commerce": project.commerce_profile,
                "drama": project.drama_profile,
            }[project.mode]
            for key, value in supplied[project.mode].model_dump().items():
                setattr(profile, key, value)
        if data.drama_style_guide is not None:
            if project.mode != "drama":
                raise ValidationException("只有 Drama Project 可以编辑风格设计。")
            for key, value in data.drama_style_guide.model_dump().items():
                setattr(project.drama_style_guide, key, value)
        await self.session.commit()
        return project

    async def delete_project(self, project_id: str):
        project = await self.get_project(project_id)
        await self.session.delete(project)
        await self.session.commit()
        return True
