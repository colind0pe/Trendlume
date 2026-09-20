from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeTaskDetailInput(BaseModel):
    type: Literal["knowledge"]
    topic: str = Field(min_length=1, max_length=500)
    audience: str = ""
    thesis: str = ""
    takeaway: str = ""
    genre: str = "auto"
    claims: list[Any] = Field(default_factory=list)
    sources: list[Any] = Field(default_factory=list)
    content_structure: dict[str, Any] = Field(default_factory=dict)
    script: dict[str, Any] = Field(default_factory=dict)
    review_status: str = "draft"


class CommerceTaskDetailInput(BaseModel):
    type: Literal["commerce"]
    creative_angle: str = Field(min_length=1, max_length=100)
    hook: str = ""
    audience: str = ""
    core_message: str = ""
    selected_claims: list[Any] = Field(default_factory=list)
    scene_outline: list[Any] = Field(default_factory=list)
    cta: str = ""
    offer: str = ""
    product_facts_version: int = Field(default=1, ge=1)
    script: dict[str, Any] = Field(default_factory=dict)
    review_status: str = "draft"


class DramaTaskDetailInput(BaseModel):
    type: Literal["drama"]
    episode_number: int = Field(ge=1)
    synopsis: str = ""
    script_text: str = ""
    continuity_data: dict[str, Any] = Field(default_factory=dict)
    review_status: str = "draft"
    production_checkpoint: dict[str, Any] = Field(default_factory=dict)


TaskDetailInput = Annotated[
    KnowledgeTaskDetailInput | CommerceTaskDetailInput | DramaTaskDetailInput,
    Field(discriminator="type"),
]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    detail: TaskDetailInput
    generation_settings: dict[str, Any] = Field(default_factory=dict)
    publishing_settings: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    detail: TaskDetailInput | None = None
    editorial_status: str | None = None
    generation_settings: dict[str, Any] | None = None
    publishing_settings: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str
    description: str
    editorial_status: str
    production_status: str
    generation_settings: dict[str, Any]
    publishing_settings: dict[str, Any]
    detail: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TaskDetailResponse(TaskResponse):
    scenes: list[Any] = Field(default_factory=list)
