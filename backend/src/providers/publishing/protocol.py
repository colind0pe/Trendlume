from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.domain.enums import PlatformType


@dataclass
class PublishResult:
    success: bool
    platform_post_id: str | None = None
    post_url: str | None = None
    error: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PublishingProvider(Protocol):
    name: str
    platform: PlatformType

    async def publish_video(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        cover_path: Path | None = None,
        credential_data: dict[str, Any] | None = None,
        custom_params: dict[str, Any] | None = None,
    ) -> PublishResult:
        """Publish video to platform and return result with post ID"""
        ...

    async def validate_account(self, credential_data: dict[str, Any]) -> bool:
        """Validate whether account credentials/tokens are valid"""
        ...
