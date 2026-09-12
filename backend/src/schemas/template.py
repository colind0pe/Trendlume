from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import AspectRatio


class TemplateParameter(BaseModel):
    name: str
    type: str = "text"
    default: Any = None
    label: str | None = None


class TemplateCatalogItem(BaseModel):
    id: str
    name: str
    version: str
    width: int
    height: int
    aspect_ratio: str = "9:16"
    media_width: int
    media_height: int
    template_type: str
    html_path: str
    preview_path: str | None = None
    parameter_schema: list[TemplateParameter] = Field(default_factory=list)
    default_params: dict[str, Any] = Field(default_factory=dict)
    supported_content_modes: list[str] = Field(default_factory=list)


class TemplatePreviewRequest(BaseModel):
    title: str = ""
    text: str = "AI 短视频模板预览"
    image_asset_id: str | None = None
    video_asset_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    custom_css: str | None = None


class ProjectTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    aspect_ratio: AspectRatio | None = None
    style_preset: str | None = None
    font_family: str | None = None
    primary_color: str | None = None
    background_color: str | None = None
    layout_type: str | None = None
    frame_template: str | None = None
    custom_css: str | None = None
    params: dict[str, Any] | None = None
    template_id: str | None = None
    template_version: str | None = None


class ProjectTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    aspect_ratio: str
    style_preset: str
    template_id: str = "default_portrait"
    template_version: str = "1"
    font_family: str
    primary_color: str
    background_color: str
    layout_type: str
    frame_template: str
    custom_css: str
    params: dict[str, Any]
    created_at: datetime
    updated_at: datetime
