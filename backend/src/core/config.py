import tomllib
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
PROJECT_FILE_PATH = ENV_FILE_PATH.with_name("pyproject.toml")


def project_version() -> str:
    with PROJECT_FILE_PATH.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


class Settings(BaseSettings):
    """Trendlume Application Deployment & Environment Settings"""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "Trendlume"
    app_version: str = Field(default_factory=project_version)
    debug: bool = False

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Paths
    base_dir: Path = Path(__file__).resolve().parent.parent.parent.parent
    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent.parent / "data"
    )
    storage_dir: Path = Field(
        default_factory=lambda: (
            Path(__file__).resolve().parent.parent.parent.parent / "data" / "storage"
        )
    )
    database_url: str = ""

    # Task Manager
    max_concurrent_workers: int = Field(
        default=2,
        ge=1,
        le=32,
        validation_alias=AliasChoices("MAX_CONCURRENT_WORKERS", "TRENDLUME_MAX_CONCURRENT_WORKERS"),
    )
    task_timeout_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices(
            "TASK_TIMEOUT_SECONDS", "TRENDLUME_TASK_TIMEOUT_SECONDS"
        ),
    )
    job_poll_interval_seconds: float = Field(default=1.0, validation_alias=AliasChoices("JOB_POLL_INTERVAL_SECONDS", "TRENDLUME_JOB_POLL_INTERVAL_SECONDS"))
    job_heartbeat_interval_seconds: float = Field(default=10.0, validation_alias=AliasChoices("JOB_HEARTBEAT_INTERVAL_SECONDS", "TRENDLUME_JOB_HEARTBEAT_INTERVAL_SECONDS"))
    job_stale_after_seconds: float = Field(default=45.0, validation_alias=AliasChoices("JOB_STALE_AFTER_SECONDS", "TRENDLUME_JOB_STALE_AFTER_SECONDS"))
    schedule_misfire_grace_seconds: float = Field(default=60.0, validation_alias=AliasChoices("SCHEDULE_MISFIRE_GRACE_SECONDS", "TRENDLUME_SCHEDULE_MISFIRE_GRACE_SECONDS"))
    max_job_retries: int = Field(default=3, ge=0, le=20, validation_alias=AliasChoices("MAX_JOB_RETRIES", "TRENDLUME_MAX_JOB_RETRIES"))

    # Project trend subscription scheduler.  Trend collection has its own
    # durable tables because it is not a Task and must never enter workflow_jobs.
    trend_scheduler_poll_interval_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=3600.0,
        validation_alias=AliasChoices(
            "TREND_SCHEDULER_POLL_INTERVAL_SECONDS",
            "TRENDLUME_TREND_SCHEDULER_POLL_INTERVAL_SECONDS",
        ),
    )
    trend_scheduler_source_timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        le=3600.0,
        validation_alias=AliasChoices(
            "TREND_SCHEDULER_SOURCE_TIMEOUT_SECONDS",
            "TRENDLUME_TREND_SCHEDULER_SOURCE_TIMEOUT_SECONDS",
        ),
    )
    trend_source_primary_url: str = Field(
        default="https://60s.viki.moe",
        validation_alias=AliasChoices(
            "TREND_SOURCE_PRIMARY_URL",
            "TRENDLUME_TREND_SOURCE_PRIMARY_URL",
        ),
    )
    trend_source_fallback_url: str = Field(
        default="https://v2.xxapi.cn",
        validation_alias=AliasChoices(
            "TREND_SOURCE_FALLBACK_URL",
            "TRENDLUME_TREND_SOURCE_FALLBACK_URL",
        ),
    )
    trend_source_request_timeout_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        validation_alias=AliasChoices(
            "TREND_SOURCE_REQUEST_TIMEOUT_SECONDS",
            "TRENDLUME_TREND_SOURCE_REQUEST_TIMEOUT_SECONDS",
        ),
    )
    trend_source_max_items: int = Field(
        default=50,
        ge=1,
        le=200,
        validation_alias=AliasChoices(
            "TREND_SOURCE_MAX_ITEMS",
            "TRENDLUME_TREND_SOURCE_MAX_ITEMS",
        ),
    )
    # Security & Encryption Root Secret (Never stored in SQLite)
    encryption_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CREDENTIAL_ENCRYPTION_KEY", "ENCRYPTION_KEY"),
    )

    # Legacy environment fallback fields (read-only for initial bootstrap migration)
    active_llm_provider: str | None = None
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    claude_api_key: str | None = None
    cloudflare_api_key: str | None = None
    custom_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    comfyui_base_url: str | None = None
    comfyui_api_key: str | None = None
    comfyui_image_workflow: str | None = None
    comfyui_video_workflow: str | None = None
    tavily_api_key: str | None = None
    pexels_api_key: str | None = None

    def model_post_init(self, __context) -> None:
        if not self.database_url:
            db_path = self.data_dir / "trendlume.db"
            # Normalize to forward slashes for sqlite URI
            db_path_str = str(db_path.resolve()).replace("\\", "/")
            self.database_url = f"sqlite+aiosqlite:///{db_path_str}"

        # Ensure base directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "assets").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "projects").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "templates").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "temp").mkdir(parents=True, exist_ok=True)


settings = Settings()
