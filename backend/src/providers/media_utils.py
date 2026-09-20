from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from src.core.exceptions import ProviderException


def local_media_data(path_or_url: str, provider: str) -> tuple[str, str]:
    """Return a MIME type and raw base64 for a local file or data URL."""
    value = str(path_or_url or "").strip()
    if value.startswith("data:"):
        try:
            header, encoded = value.split(",", 1)
            mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
            base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ProviderException(provider, "参考素材 Data URL 无效。") from exc
        return mime_type, encoded

    path = Path(value)
    if not path.is_file():
        raise ProviderException(provider, f"参考素材不存在: {value}")
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return mime_type, base64.b64encode(path.read_bytes()).decode("ascii")


def media_data_url(path_or_url: str, provider: str) -> str:
    value = str(path_or_url or "").strip()
    if value.startswith(("http://", "https://", "data:")):
        return value
    mime_type, encoded = local_media_data(value, provider)
    return f"data:{mime_type};base64,{encoded}"


def output_dimensions(
    aspect_ratio: str,
    width: int | None,
    height: int | None,
    *,
    landscape: tuple[int, int] = (1280, 720),
    portrait: tuple[int, int] = (720, 1280),
    square: tuple[int, int] = (1024, 1024),
) -> tuple[int, int]:
    if width and height and width > 0 and height > 0:
        return int(width), int(height)
    return {"16:9": landscape, "9:16": portrait, "1:1": square}.get(aspect_ratio, portrait)
