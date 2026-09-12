from __future__ import annotations

from pathlib import Path

from src.core.exceptions import ProviderException
from src.providers.materials._http import StockVideoProvider, safe_pexels_page_url
from src.providers.materials.protocol import MaterialCandidate, MaterialDownload


class PexelsVideoProvider(StockVideoProvider):
    name = "pexels"
    cache_version = 4
    API_URL = "https://api.pexels.com/v1/videos"
    VIDEO_DETAIL_URL = "https://api.pexels.com/v1/videos/videos"
    api_host = "api.pexels.com"

    def __init__(self, *args, min_short_edge: int = 720, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.min_short_edge = max(1, int(min_short_edge))
        self._renditions: dict[str, list[dict]] = {}
        self._preferred_sizes: dict[str, tuple[int, int]] = {}

    @property
    def cache_fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "version": self.cache_version,
            "locale": self.locale,
            "size": self.size,
            "min_short_edge": self.min_short_edge,
        }

    async def search(
        self,
        keyword: str,
        aspect_ratio: str = "9:16",
        min_duration_seconds: float = 0.0,
        limit: int = 20,
        *,
        target_width: int | None = None,
        target_height: int | None = None,
    ) -> list[MaterialCandidate]:
        orientation = {"9:16": "portrait", "16:9": "landscape", "1:1": "square"}.get(aspect_ratio)
        if not orientation:
            raise ProviderException(self.name, f"不支持的画幅比例: {aspect_ratio}")
        body = await self.get_json(
            f"{self.API_URL}/search",
            params={
                "query": keyword.strip(),
                "orientation": orientation,
                "size": self.size,
                "locale": self.locale,
                "per_page": max(1, min(80, int(limit))),
            },
            headers=self.headers,
        )
        candidates: list[MaterialCandidate] = []
        for item in body.get("videos") or []:
            if not isinstance(item, dict):
                continue
            try:
                duration = float(item.get("duration") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            video_id = str(item.get("id") or "").strip()
            if not video_id.isdigit():
                continue
            renditions = item.get("video_files") or []
            rendition = self.pick_rendition(
                renditions,
                aspect_ratio,
                min_short_edge=self.min_short_edge,
                target_width=target_width,
                target_height=target_height,
            )
            if duration < float(min_duration_seconds or 0) or not video_id or not rendition:
                continue
            user = item.get("user") if isinstance(item.get("user"), dict) else {}
            page_url = safe_pexels_page_url(
                item.get("url") or f"https://www.pexels.com/video/{video_id}/"
            )
            page_url = page_url or f"https://www.pexels.com/video/{video_id}/"
            author = str(user.get("name") or "").strip() or None
            author_url = safe_pexels_page_url(user.get("url"), author=True)
            self._renditions[video_id] = list(renditions)
            if rendition.get("width") and rendition.get("height"):
                self._preferred_sizes[video_id] = (rendition["width"], rendition["height"])
            candidates.append(
                MaterialCandidate(
                    provider=self.name,
                    external_id=video_id,
                    title=str(item.get("title") or f"Pexels {video_id}"),
                    source_page_url=page_url,
                    author=author,
                    author_url=author_url,
                    duration_seconds=duration,
                    width=rendition.get("width"),
                    height=rendition.get("height"),
                )
            )
        return candidates

    async def search_videos(self, request) -> list[MaterialCandidate]:
        return await self.search(
            request.keyword,
            request.aspect_ratio,
            request.min_duration_seconds,
            request.limit,
            target_width=getattr(request, "target_width", None),
            target_height=getattr(request, "target_height", None),
        )

    def set_preferred_rendition(
        self,
        external_id: str,
        width: object,
        height: object,
    ) -> None:
        try:
            parsed_width, parsed_height = int(width), int(height)
        except (TypeError, ValueError):
            return
        if parsed_width > 0 and parsed_height > 0:
            self._preferred_sizes[str(external_id)] = (parsed_width, parsed_height)

    async def download(
        self,
        external_id: str,
        aspect_ratio: str = "9:16",
        destination: Path | None = None,
    ) -> MaterialDownload:
        if destination is None:
            raise ProviderException(self.name, "在线素材下载需要提供临时文件路径。")
        external_id = str(external_id).strip()
        if not external_id or not external_id.isdigit():
            raise ProviderException(self.name, "缺少 Pexels 素材 ID。")
        renditions = self._renditions.get(external_id)
        if not renditions:
            body = await self.get_json(f"{self.VIDEO_DETAIL_URL}/{external_id}", headers=self.headers)
            renditions = body.get("video_files") or []
            self._renditions[external_id] = list(renditions)
        target_size = self._preferred_sizes.get(external_id)
        rendition = self.pick_rendition(
            renditions,
            aspect_ratio,
            min_short_edge=self.min_short_edge,
            target_width=target_size[0] if target_size else None,
            target_height=target_size[1] if target_size else None,
        )
        if not rendition:
            raise ProviderException(self.name, "Pexels 未返回符合画幅和清晰度要求的 MP4。")
        link = str(rendition.get("link") or "")
        download = await self.download_url(
            link,
            destination,
            f"pexels-{external_id}.mp4",
        )
        return download
