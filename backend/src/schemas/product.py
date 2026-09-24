from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.asset import AssetResponse

ProductFactSource = Literal["user_input", "manual_correction", "json_ld", "opengraph", "page_structure"]
FactCertainty = Literal["user_asserted", "source_reported", "uncertain"]
ClaimType = Literal["selling_point", "numerical"]


class ProductFact(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    field: str = Field(min_length=1, max_length=120)
    value: Any
    source_type: ProductFactSource
    source_ref: str = Field(min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    certainty: FactCertainty = "source_reported"
    user_confirmed: bool = False


class ProductClaim(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1000)
    claim_type: ClaimType = "selling_point"
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    certainty: FactCertainty = "uncertain"


class ProductTruthSheet(BaseModel):
    product_id: str = ""
    version: int = 1
    facts: list[ProductFact] = Field(default_factory=list, max_length=100)
    selling_points: list[ProductClaim] = Field(default_factory=list, max_length=30)
    numerical_claims: list[ProductClaim] = Field(default_factory=list, max_length=30)
    unresolved_fields: list[str] = Field(default_factory=list, max_length=30)
    generated_at: str | None = None


class ProductAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    asset_id: str | None = None
    asset_type: str
    role: str
    source_kind: str
    source_url: str | None = None
    alt_text: str
    sort_order: int
    metadata_json: dict[str, Any]
    created_at: datetime
    asset: AssetResponse | None = None


class ProductClaimInput(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    claim_type: ClaimType = "selling_point"
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class ProductCreate(BaseModel):
    title: str = Field(default="", max_length=500)
    name: str | None = Field(default=None, max_length=500)
    brand: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=10000)
    price: str = Field(default="", max_length=100)
    currency: str = Field(default="", max_length=20)
    specifications: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = Field(default=None, max_length=2000)
    selling_points: list[ProductClaimInput] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def require_title(self) -> ProductCreate:
        if not self.title.strip() and self.name:
            self.title = self.name.strip()
        if not self.title.strip():
            raise ValueError("商品名称不能为空。")
        self.title = self.title.strip()
        return self


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    brand: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    price: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, max_length=20)
    specifications: dict[str, Any] | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    selling_points: list[ProductClaimInput] | None = Field(default=None, max_length=30)


class ProductTruthSheetUpdate(BaseModel):
    truth_sheet: ProductTruthSheet


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    brand: str
    description: str
    price: str
    currency: str
    specifications: dict[str, Any]
    source_url: str | None = None
    source_snapshot: dict[str, Any]
    truth_sheet: ProductTruthSheet
    status: str
    assets: list[ProductAssetResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
