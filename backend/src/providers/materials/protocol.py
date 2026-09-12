from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class MaterialCandidate:
    """Public metadata for an online stock-video candidate.

    Download links deliberately are not part of the public DTO.  Providers
    resolve a fresh rendition when an import is requested, which avoids
    persisting short-lived CDN URLs in task or asset metadata.
    """

    provider: str
    external_id: str
    title: str
    source_page_url: str | None = None
    author: str | None = None
    author_url: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class MaterialDownload:
    """A verified provider download written to a caller-owned temp file."""

    file_path: Path
    file_name: str
    mime_type: str = "video/mp4"
    size_bytes: int = 0


@runtime_checkable
class MaterialProvider(Protocol):
    name: str

    async def search(
        self,
        keyword: str,
        aspect_ratio: str = "9:16",
        min_duration_seconds: float = 0.0,
        limit: int = 20,
    ) -> list[MaterialCandidate]:
        ...

    async def download(
        self,
        external_id: str,
        aspect_ratio: str = "9:16",
        destination: Path | None = None,
    ) -> MaterialDownload:
        ...

    async def search_videos(self, request) -> list[MaterialCandidate]:
        """Compatibility helper for callers using a request object."""
        ...
