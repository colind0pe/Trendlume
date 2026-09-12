import posixpath
from enum import StrEnum

BGM_STORAGE_PREFIX = "audio/bgm/"


def normalize_storage_path(file_path: str | None) -> str:
    """Normalize stored asset paths before applying storage-boundary checks."""
    if not file_path:
        return ""
    return posixpath.normpath(str(file_path).replace("\\", "/")).lstrip("/")


def is_bgm_storage_path(file_path: str | None) -> bool:
    """Return whether a path is inside the canonical BGM storage directory."""
    return normalize_storage_path(file_path).startswith(BGM_STORAGE_PREFIX)


class AspectRatio(StrEnum):
    PORTRAIT_9_16 = "9:16"
    LANDSCAPE_16_9 = "16:9"
    SQUARE_1_1 = "1:1"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    CONFIGURED = "configured"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    BGM = "bgm"
    FONT = "font"


class JobType(StrEnum):
    SCRIPT_GENERATION = "script_generation"
    TTS_GENERATION = "tts_generation"
    MEDIA_GENERATION = "media_generation"
    FRAME_RENDERING = "frame_rendering"
    VIDEO_COMPOSITION = "video_composition"
    FULL_PIPELINE = "full_pipeline"
    PUBLISH = "publish"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    QUEUED = "queued"
    MISSED = "missed"
    UNCERTAIN = "uncertain"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class PlatformType(StrEnum):
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    BILIBILI = "bilibili"
    WECHAT_VIDEO = "wechat_video"
    TIKTOK = "tiktok"
    MOCK = "mock"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    ERROR = "error"


class CredentialType(StrEnum):
    COOKIE = "cookie"
    TOKEN = "token"
    API_KEY = "api_key"


class PublishJobStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MISSED = "missed"
    UNCERTAIN = "uncertain"
