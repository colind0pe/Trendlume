from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProviderConfigBase(BaseModel):
    provider_type: str = Field(..., description="Provider category (llm, search, image, video, tts, material, publishing)")
    provider_name: str = Field(..., description="Provider engine name (openai, deepseek, tavily, comfyui, volcengine, edge_tts, etc.)")
    display_name: str = Field(..., description="Human-readable title")
    enabled: bool = Field(default=True, description="Whether this provider is currently enabled")
    is_default: bool = Field(default=False, description="Whether this is the primary default provider for its category")
    config: dict[str, Any] = Field(default_factory=dict, description="Non-sensitive runtime parameters")


class ProviderConfigCreate(ProviderConfigBase):
    id: str | None = Field(default=None, description="Optional custom ID (e.g. prov_llm_deepseek)")
    credentials: dict[str, Any] | None = Field(
        default=None, description="Plaintext credentials to be encrypted (api_key, client_secret, token, etc.)"
    )


class ProviderConfigUpdate(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    config: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = Field(
        default=None,
        description="Updated credentials. Masked placeholders (e.g. containing '••••') will preserve existing values.",
    )


class ProviderConfigResponse(BaseModel):
    id: str
    provider_type: str
    provider_name: str
    display_name: str
    enabled: bool
    is_default: bool
    config: dict[str, Any]
    masked_credentials: dict[str, str] = Field(
        default_factory=dict, description="Masked credentials safe for frontend presentation"
    )
    has_credentials: bool = Field(default=False, description="Whether valid credentials exist for this provider")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProviderTestRequest(BaseModel):
    provider_id: str | None = None
    provider_type: str | None = None
    provider_name: str | None = None
    config: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    test_payload: dict[str, Any] | None = None


class ProviderTestResponse(BaseModel):
    connected: bool
    message: str
    latency_ms: float | None = None
    details: dict[str, Any] | None = None
