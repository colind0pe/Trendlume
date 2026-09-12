from dataclasses import dataclass
from typing import Protocol, runtime_checkable

DEFAULT_IMAGE_TEST_PROMPT = "一只橘猫坐在窗边，温暖阳光"


@dataclass
class ImageResult:
    image_bytes: bytes
    mime_type: str = "image/png"
    width: int = 1080
    height: int = 1920
    format: str = "png"


@runtime_checkable
class ImageProvider(Protocol):
    name: str

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        style_preset: str = "cinematic",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> ImageResult:
        """Generate high resolution visual image for a storyboard scene"""
        ...
