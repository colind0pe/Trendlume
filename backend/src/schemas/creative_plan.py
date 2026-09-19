from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import CreativeAngle, VisualRole

CreativePlanStatus = Literal["draft", "selected", "variant", "archived"]
CreativePlanFindingSeverity = Literal["pass", "warning", "error"]


class CreativePlanClaim(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1000)
    claim_type: Literal["selling_point", "numerical"] = "selling_point"
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class CreativeSceneOutline(BaseModel):
    sequence_index: int = Field(default=0, ge=0)
    beat: str = Field(min_length=1, max_length=160)
    visual: str = Field(min_length=1, max_length=1000)
    narration: str = Field(min_length=1, max_length=1000)
    visual_role: VisualRole = VisualRole.CONTEXT
    claim_refs: list[str] = Field(default_factory=list, max_length=20)
    asset_strategy: Literal["product_asset", "deterministic_layout", "generated_context"] = (
        "deterministic_layout"
    )


class CreativePlanGenerateRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=3)
    audience: str = Field(default="", max_length=500)
    objective: str = Field(default="", max_length=500)


class CreativePlanDuplicateRequest(BaseModel):
    variant_label: str | None = Field(default=None, max_length=100)


class CreativePlanConfirmFactsRequest(BaseModel):
    confirm: bool = True


class CreativePlanProduceRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    title: str | None = Field(default=None, max_length=255)


class CreativePlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    source_plan_id: str | None = None
    status: CreativePlanStatus
    variant_label: str
    variant_index: int
    angle: CreativeAngle
    hook: str
    audience: str
    core_message: str
    claims: list[CreativePlanClaim]
    scene_outline: list[CreativeSceneOutline]
    cta: str
    truth_sheet_version: int
    fact_snapshot: dict[str, Any]
    selected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CommercePreflightFinding(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    severity: CreativePlanFindingSeverity
    message: str = Field(min_length=1, max_length=1000)
    scene_ids: list[str] = Field(default_factory=list, max_length=20)


class CommercePreflightResponse(BaseModel):
    task_id: str
    status: Literal["pass", "warning", "fail"]
    blocking: bool
    checked_at: datetime
    findings: list[CommercePreflightFinding]
    summary: dict[str, Any] = Field(default_factory=dict)
