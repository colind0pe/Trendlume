from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeProfileInput(BaseModel):
    positioning: str = ""
    domain: str = ""
    default_audience: str = ""
    tone: str = ""
    visual_system: dict[str, Any] = Field(default_factory=dict)
    evidence_strategy: dict[str, Any] = Field(default_factory=dict)


class KnowledgeProfileResponse(KnowledgeProfileInput):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    revision: int
    created_at: datetime
    updated_at: datetime


class CommerceProfileInput(BaseModel):
    brand: str = Field(default="", max_length=255)
    market: str = Field(default="", max_length=255)
    audience: str = Field(default="", max_length=1000)
    marketing_goal: str = Field(default="", max_length=2000)
    brand_tone: str = Field(default="", max_length=255)
    visual_system: dict[str, Any] = Field(default_factory=dict)
    default_cta: str = Field(default="", max_length=1000)
    compliance_limits: list[Any] = Field(default_factory=list, max_length=50)
    platform_defaults: dict[str, Any] = Field(default_factory=dict)


class CommerceProfileResponse(CommerceProfileInput):
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    revision: int
    created_at: datetime
    updated_at: datetime


class KnowledgeContentItemCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    audience: str = Field(default="", max_length=500)
    thesis: str = ""
    takeaway: str = ""
    genre: str = Field(default="auto", max_length=100)
    key_claims: list[Any] = Field(default_factory=list)
    source_refs: list[Any] = Field(default_factory=list)
    review_status: str = Field(default="draft", min_length=1, max_length=30)


class KnowledgeContentItemUpdate(BaseModel):
    topic: str | None = Field(default=None, min_length=1, max_length=500)
    audience: str | None = Field(default=None, max_length=500)
    thesis: str | None = None
    takeaway: str | None = None
    genre: str | None = Field(default=None, max_length=100)
    key_claims: list[Any] | None = None
    source_refs: list[Any] | None = None
    review_status: str | None = Field(default=None, min_length=1, max_length=30)


class KnowledgeContentItemResponse(KnowledgeContentItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    revision: int
    created_at: datetime
    updated_at: datetime
