from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.enums import CredentialType, PlatformType

# ============================================================================
# Credentials
# ============================================================================


class CredentialCreate(BaseModel):
    platform: PlatformType
    credential_type: CredentialType = CredentialType.COOKIE
    payload: dict[str, Any]


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    credential_type: str
    is_valid: bool
    expires_at: datetime | None = None
    created_at: datetime


# ============================================================================
# Social Accounts
# ============================================================================


class SocialAccountCreate(BaseModel):
    platform: PlatformType
    account_name: str
    username: str = ""
    avatar_url: str | None = None
    credential_id: str | None = None


class SocialAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    account_name: str
    username: str
    avatar_url: str | None = None
    status: str
    credential_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AccountCheckResponse(BaseModel):
    account_id: str
    is_valid: bool
    username: str | None = None
    display_name: str | None = None
    error_message: str | None = None
    checked_at: str


# ============================================================================
# Interactive QR Code Login (Douyin, Mock)
# ============================================================================


class QRStartRequest(BaseModel):
    platform: str = Field(default="douyin", description="Platform identifier (e.g. douyin)")
    headless: bool = Field(default=True, description="Run browser in headless mode")


class QRStartResponse(BaseModel):
    session_id: str
    platform: str
    status: str
    qrcode_data_url: str | None = None


class QRStatusResponse(BaseModel):
    session_id: str
    platform: str
    status: str
    qrcode_data_url: str | None = None
    is_logged_in: bool = False
    error_message: str | None = None


class QRCompleteRequest(BaseModel):
    session_id: str
    account_name: str = Field(default="我的抖音号", description="Custom alias for the account")
    username: str | None = None


class ManualCookieImportRequest(BaseModel):
    platform: str = Field(default="douyin", description="Platform identifier")
    account_name: str = Field(description="Account alias")
    cookie_string: str = Field(description="Raw cookie string or StorageState JSON")
    username: str | None = ""


# ============================================================================
# Publish Tasks & Jobs
# ============================================================================


class TaskPublishRequest(BaseModel):
    account_id: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    cover_asset_id: str | None = None


class TaskScheduleRequest(BaseModel):
    scheduled_at: datetime
    account_id: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    cover_asset_id: str | None = None


class UncertainPublishResolveRequest(BaseModel):
    action: str = Field(description="retry or acknowledge")


class PublishingJobCreate(BaseModel):
    project_id: str
    video_asset_id: str
    account_id: str
    platform: PlatformType
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    cover_asset_id: str | None = None
    scheduled_at: datetime | None = None
    custom_params: dict[str, Any] = Field(default_factory=dict)


class PublishingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str | None = None
    id: str
    project_id: str
    video_asset_id: str
    account_id: str
    platform: str
    title: str
    description: str
    tags: list[str]
    cover_asset_id: str | None = None
    status: str
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    attempt_count: int
    max_attempts: int
    error_message: str | None = None
    platform_post_id: str | None = None
    custom_params: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @field_validator("scheduled_at", "published_at", "created_at", "updated_at", mode="before")
    @classmethod
    def normalize_utc(cls, value: datetime | str | None) -> datetime | str | None:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


# ============================================================================
# Interactive Verification Requests (SMS / 2FA)
# ============================================================================


class VerificationRequestResponse(BaseModel):
    request_id: str
    job_id: str
    account_id: str
    account_name: str = ""
    title: str = ""
    platform: str
    prompt: str
    status: str
    remaining_seconds: int
    timeout_seconds: float
    created_at: float
    error_message: str | None = None


class VerificationSubmitRequest(BaseModel):
    request_id: str
    code: str = Field(min_length=1, max_length=30)


class VerificationCancelRequest(BaseModel):
    request_id: str
