from __future__ import annotations

import asyncio
import time

import httpx

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.media_utils import local_media_data, output_dimensions
from src.providers.video.protocol import VideoResult


class GoogleVideoProvider:
    """Veo 3.1 video generation with references and first/last frames."""

    name = "google"
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    DEFAULT_MODEL = "veo-3.1-generate-preview"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        generation_timeout: float = 1800.0,
        poll_interval: float = 10.0,
        resolution: str = "720p",
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = str(model or self.DEFAULT_MODEL).strip()
        self.timeout = float(timeout)
        self.generation_timeout = float(generation_timeout)
        self.poll_interval = max(1.0, float(poll_interval))
        self.resolution = str(resolution or "720p")

    def _image(self, value: str) -> dict:
        mime_type, encoded = local_media_data(value, self.name)
        return {"inlineData": {"mimeType": mime_type, "data": encoded}}

    async def generate_video(
        self,
        prompt: str,
        image_url: str | None = None,
        aspect_ratio: str = "9:16",
        duration_seconds: float = 4.0,
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
        last_frame_url: str | None = None,
        reference_image_urls: list[str] | None = None,
    ) -> VideoResult:
        del workflow
        if not self.api_key:
            raise ProviderException(self.name, "Google Gemini 未配置 API Key。")
        if last_frame_url and not image_url:
            raise ProviderException(self.name, "Veo 使用尾帧时必须同时提供首帧。")
        references = list(reference_image_urls or [])
        if len(references) > 3:
            raise ProviderException(self.name, "Veo 3.1 最多支持 3 张角色或道具参考图。")
        if references and (image_url or last_frame_url):
            raise ProviderException(
                self.name,
                "Veo 参考图模式不能与首尾帧插值同时使用；请在短剧镜头中选择一种约束方式。",
            )
        allowed_durations = (4, 6, 8)
        requested = float(duration_seconds or 4.0)
        duration = min(allowed_durations, key=lambda value: abs(value - requested))
        instance: dict = {"prompt": prompt}
        if image_url:
            instance["image"] = self._image(image_url)
        if last_frame_url:
            instance["lastFrame"] = self._image(last_frame_url)
        if references:
            instance["referenceImages"] = [
                {"image": self._image(item), "referenceType": "asset"} for item in references
            ]
        payload = {
            "instances": [instance],
            "parameters": {
                "aspectRatio": aspect_ratio if aspect_ratio in {"9:16", "16:9"} else "16:9",
                "durationSeconds": str(duration),
                "resolution": self.resolution,
                "numberOfVideos": 1,
            },
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, follow_redirects=True
            ) as client:
                response = await client.post(
                    f"{self.base_url}/models/{self.model}:predictLongRunning",
                    headers=headers,
                    json=payload,
                )
                body = self._body(response, "创建 Veo 视频任务")
                operation = body.get("name")
                if not operation:
                    raise ProviderException(self.name, "Veo 创建响应中没有 operation name。")
                video_url = await self._poll(client, str(operation), headers)
                download = await client.get(video_url, headers={"x-goog-api-key": self.api_key})
                if not download.is_success or not download.content:
                    raise ProviderException(
                        self.name, f"下载 Veo 视频失败 HTTP {download.status_code}。"
                    )
                output_width, output_height = output_dimensions(aspect_ratio, width, height)
                return VideoResult(
                    download.content,
                    float(duration),
                    output_width,
                    output_height,
                    "mp4",
                    "video/mp4",
                )
        except ProviderException:
            raise
        except httpx.RequestError as exc:
            raise ProviderException(self.name, f"连接 Google Veo 失败: {exc}") from exc

    async def _poll(
        self, client: httpx.AsyncClient, operation: str, headers: dict[str, str]
    ) -> str:
        deadline = time.monotonic() + self.generation_timeout
        while True:
            response = await client.get(f"{self.base_url}/{operation}", headers=headers)
            body = self._body(response, "查询 Veo 视频任务")
            if body.get("done"):
                if body.get("error"):
                    raise ProviderException(self.name, f"Veo 视频任务失败: {body['error']}")
                samples = ((body.get("response") or {}).get("generateVideoResponse") or {}).get(
                    "generatedSamples"
                ) or []
                video = samples[0].get("video") if samples else None
                if not isinstance(video, dict) or not video.get("uri"):
                    raise ProviderException(self.name, "Veo 视频任务成功但没有下载 URI。")
                return str(video["uri"])
            if time.monotonic() >= deadline:
                raise ProviderException(
                    self.name,
                    f"Veo 视频任务等待超时 ({self.generation_timeout}s，operation={operation})。",
                )
            await asyncio.sleep(self.poll_interval)

    def _body(self, response: httpx.Response, action: str) -> dict:
        if not response.is_success:
            raise ProviderException(
                self.name,
                f"{action}失败 HTTP {response.status_code}: {redact_sensitive_text(response.text[:500])}",
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderException(self.name, f"{action}返回了无效 JSON。") from exc
