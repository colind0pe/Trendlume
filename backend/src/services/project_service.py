import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundException, ValidationException
from src.domain.enums import AssetType, ProductionMode, ProjectStatus
from src.models.asset import AssetModel
from src.models.project import ProjectModel
from src.models.project_context import (
    CommerceProjectProfileModel,
    KnowledgeProjectProfileModel,
)
from src.models.template import ProjectTemplateModel
from src.repositories.project_repository import ProjectRepository
from src.repositories.template_repository import ProjectTemplateRepository
from src.schemas.project import ProjectCreate, ProjectUpdate
from src.services.system_asset_service import ensure_default_bgm


class ProjectService:
    """Application service for Project lifecycle"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.template_repo = ProjectTemplateRepository(session)

    async def create_project(self, data: ProjectCreate) -> ProjectModel:
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        template_id = f"tpl_{uuid.uuid4().hex[:12]}"

        if data.primary_production_mode != ProductionMode.KNOWLEDGE and data.knowledge_profile:
            raise ValidationException("Knowledge profile 只能用于 Knowledge Project。")
        if data.primary_production_mode != ProductionMode.COMMERCE and data.commerce_profile:
            raise ValidationException("Commerce profile 只能用于 Commerce Project。")

        default_bgm = None
        try:
            default_bgm = await ensure_default_bgm(self.session)
        except Exception:
            # Project creation remains available when the optional local media
            # toolchain is not installed.  Application startup reports the
            # initialization problem and leaves the project without a default.
            default_bgm = None

        selected_bgm_id = data.bgm_asset_id or (default_bgm.id if default_bgm else None)
        if data.bgm_asset_id:
            selected_asset = await self.session.get(AssetModel, data.bgm_asset_id)
            is_system = bool(
                selected_asset
                and selected_asset.project_id is None
                and (selected_asset.metadata_json or {}).get("scope") == "system"
            )
            if not selected_asset or not is_system:
                raise ValidationException("新项目只能选择系统 BGM 作为初始默认素材。")
            if selected_asset.asset_type not in {AssetType.AUDIO.value, AssetType.BGM.value}:
                raise ValidationException("项目默认 BGM 必须是音频文件。")

        # 1. Create Project
        project = ProjectModel(
            id=project_id,
            name=data.name,
            description=data.description,
            aspect_ratio=data.aspect_ratio.value,
            primary_production_mode=data.primary_production_mode.value,
            status=ProjectStatus.DRAFT.value,
            default_voice_id=data.default_voice_id,
            bgm_asset_id=selected_bgm_id,
            settings=data.settings,
        )
        await self.project_repo.create(project)

        # 2. Automatically create 1:1 ProjectTemplate
        aspect = data.aspect_ratio.value
        if aspect == "16:9":
            default_tid = "image_wide_minimal"
            default_frame = "1920x1080/image_wide_minimal.html"
        elif aspect == "1:1":
            default_tid = "image_square_matted"
            default_frame = "1080x1080/image_square_matted.html"
        else:
            default_tid = "image_gallery_matted"
            default_frame = "1080x1920/image_gallery_matted.html"

        template = ProjectTemplateModel(
            id=template_id,
            project_id=project_id,
            name=f"{data.name} 默认模版",
            aspect_ratio=aspect,
            template_id=default_tid,
            template_version="1",
            style_preset="modern_clean",
            font_family="Inter, sans-serif",
            primary_color="#a855f7",
            background_color="#0f172a",
            layout_type="split_card",
            frame_template=default_frame,
            custom_css="",
            params={},
        )
        await self.template_repo.create(template)
        if data.primary_production_mode == ProductionMode.KNOWLEDGE:
            profile_values = (
                data.knowledge_profile.model_dump()
                if data.knowledge_profile
                else {}
            )
            self.session.add(
                KnowledgeProjectProfileModel(project_id=project_id, **profile_values)
            )
        elif data.primary_production_mode == ProductionMode.COMMERCE:
            profile_values = (
                data.commerce_profile.model_dump()
                if data.commerce_profile
                else {}
            )
            self.session.add(
                CommerceProjectProfileModel(project_id=project_id, **profile_values)
            )
        await self.session.commit()

        # Re-fetch with template
        return await self.get_project(project_id)

    async def get_project(self, project_id: str) -> ProjectModel:
        project = await self.project_repo.get_with_template(project_id)
        if not project:
            raise NotFoundException("Project", project_id)
        return project

    async def get_project_detail(self, project_id: str) -> ProjectModel:
        project = await self.project_repo.get_with_details(project_id)
        if not project:
            raise NotFoundException("Project", project_id)
        return project

    async def list_projects(self, limit: int = 50, offset: int = 0) -> Sequence[ProjectModel]:
        return await self.project_repo.list_recent(limit=limit, offset=offset)

    async def update_project(self, project_id: str, data: ProjectUpdate) -> ProjectModel:
        project = await self.get_project(project_id)
        if data.name is not None:
            project.name = data.name
        if data.description is not None:
            project.description = data.description
        if data.aspect_ratio is not None:
            project.aspect_ratio = data.aspect_ratio.value
        if data.primary_production_mode is not None:
            requested_mode = data.primary_production_mode.value
            current_mode = project.primary_production_mode or ProductionMode.KNOWLEDGE.value
            if requested_mode != current_mode:
                raise ValidationException("项目生产模式在创建时确定，创建后不能切换。")
        if data.status is not None:
            project.status = data.status.value
        if data.cover_asset_id is not None:
            project.cover_asset_id = data.cover_asset_id
        if data.default_voice_id is not None:
            project.default_voice_id = data.default_voice_id
        if "bgm_asset_id" in data.model_fields_set:
            if data.bgm_asset_id:
                asset = await self.session.get(AssetModel, data.bgm_asset_id)
                is_system = bool(
                    asset
                    and asset.project_id is None
                    and (asset.metadata_json or {}).get("scope") == "system"
                )
                if not asset or (asset.project_id != project_id and not is_system):
                    raise ValidationException("背景音乐不存在或不属于当前项目。")
                if asset.asset_type not in {AssetType.AUDIO.value, AssetType.BGM.value}:
                    raise ValidationException("背景音乐必须是音频或 BGM 素材。")
            project.bgm_asset_id = data.bgm_asset_id
        if data.settings is not None:
            project.settings = data.settings

        await self.project_repo.update(project)
        await self.session.commit()
        return await self.get_project(project_id)

    async def delete_project(self, project_id: str) -> bool:
        project = await self.get_project(project_id)
        res = await self.project_repo.delete_by_id(project.id)
        await self.session.commit()
        return res
