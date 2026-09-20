from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import AspectRatio, ProductionMode, ProjectStatus
from src.schemas.project_context import CommerceProfileInput, KnowledgeProfileInput
from src.schemas.task import TaskResponse
from src.schemas.template import ProjectTemplateResponse


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    aspect_ratio: AspectRatio = Field(default=AspectRatio.PORTRAIT_9_16)
    primary_production_mode: ProductionMode = ProductionMode.KNOWLEDGE
    default_voice_id: str | None = "zh-CN-YunxiNeural"
    bgm_asset_id: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    knowledge_profile: KnowledgeProfileInput | None = None
    commerce_profile: CommerceProfileInput | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    aspect_ratio: AspectRatio | None = None
    primary_production_mode: ProductionMode | None = None
    status: ProjectStatus | None = None
    cover_asset_id: str | None = None
    default_voice_id: str | None = None
    bgm_asset_id: str | None = None
    settings: dict[str, Any] | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    aspect_ratio: str
    primary_production_mode: str
    status: str
    cover_asset_id: str | None = None
    default_voice_id: str | None = None
    bgm_asset_id: str | None = None
    settings: dict[str, Any]
    template: ProjectTemplateResponse | None = None
    created_at: datetime
    updated_at: datetime


class ProjectDetailResponse(ProjectResponse):
    tasks: list[TaskResponse] = Field(default_factory=list)
