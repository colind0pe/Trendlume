from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException
from src.models.template import ProjectTemplateModel
from src.repositories.project_repository import ProjectRepository
from src.repositories.template_repository import ProjectTemplateRepository
from src.schemas.template import ProjectTemplateUpdate
from src.services.template_catalog import template_catalog


class ProjectTemplateService:
    """Application service for Project Template management"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.template_repo = ProjectTemplateRepository(session)
        self.project_repo = ProjectRepository(session)

    async def get_template_by_project(self, project_id: str) -> ProjectTemplateModel:
        # Ensure project exists
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundException("Project", project_id)

        template = await self.template_repo.get_by_project_id(project_id)
        if not template:
            raise NotFoundException("ProjectTemplate", f"for project {project_id}")
        return template

    async def update_template(
        self, project_id: str, data: ProjectTemplateUpdate
    ) -> ProjectTemplateModel:
        template = await self.get_template_by_project(project_id)
        if data.name is not None:
            template.name = data.name
        if data.aspect_ratio is not None:
            template.aspect_ratio = data.aspect_ratio.value
        if data.style_preset is not None:
            template.style_preset = data.style_preset
        if data.template_id is not None:
            catalog_item = template_catalog.get(data.template_id)
            if not catalog_item:
                raise NotFoundException("Template", data.template_id)
            template.template_id = catalog_item["id"]
            template.template_version = data.template_version or catalog_item["version"]
            template.frame_template = catalog_item["html_path"]
        elif data.template_version is not None:
            template.template_version = data.template_version
        if data.font_family is not None:
            template.font_family = data.font_family
        if data.primary_color is not None:
            template.primary_color = data.primary_color
        if data.background_color is not None:
            template.background_color = data.background_color
        if data.layout_type is not None:
            template.layout_type = data.layout_type
        if data.frame_template is not None:
            template.frame_template = data.frame_template
        if data.custom_css is not None:
            template.custom_css = data.custom_css
        if data.params is not None:
            template.params = data.params

        return await self.template_repo.update(template)
