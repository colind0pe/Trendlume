from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DramaCharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    appearance_rules: dict[str, Any] = Field(default_factory=dict)
    wardrobe_rules: dict[str, Any] = Field(default_factory=dict)
    voice_id: str | None = Field(default=None, max_length=120)


class DramaCharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    appearance_rules: dict[str, Any] | None = None
    wardrobe_rules: dict[str, Any] | None = None
    voice_id: str | None = Field(default=None, max_length=120)


class DramaCharacterResponse(DramaCharacterCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    approval_status: str
    created_at: datetime
    updated_at: datetime


class DramaLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    visual_description: str = ""
    continuity_data: dict[str, Any] = Field(default_factory=dict)


class DramaLocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    visual_description: str | None = None
    continuity_data: dict[str, Any] | None = None


class DramaLocationResponse(DramaLocationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    approval_status: str


class DramaPropCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    continuity_data: dict[str, Any] = Field(default_factory=dict)


class DramaPropUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    continuity_data: dict[str, Any] | None = None


class DramaPropResponse(DramaPropCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    approval_status: str
