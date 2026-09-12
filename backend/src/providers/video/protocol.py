from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class VideoResult:
    video_bytes: bytes
    duration_seconds: float = 4.0
    width: int = 720
    height: int = 1280
    format: str = "mp4"
    mime_type: str = "video/mp4"


@runtime_checkable
class VideoProvider(Protocol):
    name: str

    async def generate_video(
        self,
        prompt: str,
        image_url: str | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: float = 4.0,
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> VideoResult:
        """Generate animated video segment for a scene"""
        ...
