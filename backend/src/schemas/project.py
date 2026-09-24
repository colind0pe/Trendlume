from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.task import TaskResponse


class KnowledgeProjectProfileInput(BaseModel):
    domain: str = ""
    positioning: str = ""
    default_audience: str = ""
    tone: str = ""
    evidence_strategy: dict[str, Any] = Field(default_factory=dict)
    visual_system: dict[str, Any] = Field(default_factory=dict)
    source_library: list[Any] = Field(default_factory=list)


class CommerceProjectProfileInput(BaseModel):
    brand: str = ""
    market: str = ""
    default_audience: str = ""
    marketing_goal: str = ""
    brand_tone: str = ""
    compliance_constraints: list[Any] = Field(default_factory=list)
    visual_system: dict[str, Any] = Field(default_factory=dict)
    default_cta: str = ""
    platform_defaults: dict[str, Any] = Field(default_factory=dict)


class DramaProjectProfileInput(BaseModel):
    series_title: str
    logline: str = ""
    genre: str = ""
    tone: str = ""
    world_setting: str = ""
    story_source: dict[str, Any] = Field(default_factory=dict)
    series_bible: dict[str, Any] = Field(default_factory=dict)
    continuity_rules: list[Any] = Field(default_factory=list)


class DramaStyleGuideInput(BaseModel):
    medium: str = ""
    art_direction: str = ""
    palette: dict[str, Any] = Field(default_factory=dict)
    lighting: dict[str, Any] = Field(default_factory=dict)
    materials: dict[str, Any] = Field(default_factory=dict)
    cinematography: dict[str, Any] = Field(default_factory=dict)
    composition: dict[str, Any] = Field(default_factory=dict)
    camera_motion: dict[str, Any] = Field(default_factory=dict)
    character_rules: dict[str, Any] = Field(default_factory=dict)
    environment_rules: dict[str, Any] = Field(default_factory=dict)
    negative_constraints: list[Any] = Field(default_factory=list)
    reference_asset_ids: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    mode: Literal["knowledge", "commerce", "drama"]
    aspect_ratio: str = "9:16"
    default_production_settings: dict[str, Any] = Field(default_factory=dict)
    knowledge_profile: KnowledgeProjectProfileInput | None = None
    commerce_profile: CommerceProjectProfileInput | None = None
    drama_profile: DramaProjectProfileInput | None = None
    drama_style_guide: DramaStyleGuideInput | None = None

    @model_validator(mode="after")
    def exactly_matching_profile(self):
        profiles = {
            "knowledge": self.knowledge_profile,
            "commerce": self.commerce_profile,
            "drama": self.drama_profile,
        }
        if (
            profiles[self.mode] is None
            or sum(value is not None for value in profiles.values()) != 1
        ):
            raise ValueError("Project 必须且只能提供与 mode 匹配的 Profile。")
        if self.mode != "drama" and self.drama_style_guide is not None:
            raise ValueError("只有 Drama Project 可以提供风格设计。")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None
    aspect_ratio: str | None = None
    default_production_settings: dict[str, Any] | None = None
    knowledge_profile: KnowledgeProjectProfileInput | None = None
    commerce_profile: CommerceProjectProfileInput | None = None
    drama_profile: DramaProjectProfileInput | None = None
    drama_style_guide: DramaStyleGuideInput | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    mode: str
    status: str
    aspect_ratio: str
    default_production_settings: dict[str, Any]
    profile: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProjectDetailResponse(ProjectResponse):
    tasks: list[TaskResponse] = Field(default_factory=list)
