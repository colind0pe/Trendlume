from __future__ import annotations

import asyncio
import time

import httpx

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.media_utils import media_data_url, output_dimensions
from src.providers.video.protocol import VideoResult


class AliyunVideoProvider:
    """Wan 2.7 text/image-to-video through Alibaba Cloud Model Studio."""

    name = "aliyun"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
    DEFAULT_MODEL = "wan2.7-i2v"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        text_model: str = "wan2.7-t2v",
        timeout: float = 60.0,
        generation_timeout: float = 1800.0,
        poll_interval: float = 10.0,
        resolution: str = "720P",
        prompt_extend: bool = True,
        watermark: bool = False,
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = str(model or self.DEFAULT_MODEL).strip()
        self.text_model = str(text_model or "wan2.7-t2v").strip()
        self.timeout = float(timeout)
        self.generation_timeout = float(generation_timeout)
        self.poll_interval = max(1.0, float(poll_interval))
        self.resolution = str(resolution or "720P").upper()
        self.prompt_extend = bool(prompt_extend)
        self.watermark = bool(watermark)

    def _headers(self, *, async_request: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if async_request:
            headers["X-DashScope-Async"] = "enable"
        return headers

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
            raise ProviderException(self.name, "阿里云百炼未配置 API Key。")
        if reference_image_urls:
            raise ProviderException(
                self.name,
                "Wan 2.7 首尾帧接口不接收额外角色参考图；请先用 Qwen Image 生成一致的首帧。",
            )
        if last_frame_url and not image_url:
            raise ProviderException(self.name, "Wan 2.7 使用尾帧时必须同时提供首帧。")
        media = []
        if image_url:
            media.append({"type": "first_frame", "url": media_data_url(image_url, self.name)})
        if last_frame_url:
            media.append({"type": "last_frame", "url": media_data_url(last_frame_url, self.name)})
        duration = min(15, max(2, int(round(float(duration_seconds or 4.0)))))
        parameters = {
            "resolution": self.resolution,
            "duration": duration,
            "prompt_extend": self.prompt_extend,
            "watermark": self.watermark,
        }
        if not media:
            parameters["ratio"] = aspect_ratio
        payload = {
            "model": self.model if media else self.text_model,
            "input": {"prompt": prompt, **({"media": media} if media else {})},
            "parameters": parameters,
        }
        create_url = f"{self.base_url}/services/aigc/video-generation/video-synthesis"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(
                    create_url, headers=self._headers(async_request=True), json=payload
                )
                body = self._body(response, "创建 Wan 视频任务")
                task_id = (body.get("output") or {}).get("task_id")
                if not task_id:
                    raise ProviderException(self.name, "Wan 视频创建响应中没有 task_id。")
                video_url = await self._poll(client, str(task_id))
                download = await client.get(video_url)
                if not download.is_success or not download.content:
                    raise ProviderException(
                        self.name, f"下载 Wan 视频失败 HTTP {download.status_code}。"
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
            raise ProviderException(self.name, f"连接阿里云百炼视频服务失败: {exc}") from exc

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> str:
        deadline = time.monotonic() + self.generation_timeout
        while True:
            response = await client.get(f"{self.base_url}/tasks/{task_id}", headers=self._headers())
            body = self._body(response, "查询 Wan 视频任务")
            output = body.get("output") or {}
            status = str(output.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                if not output.get("video_url"):
                    raise ProviderException(self.name, "Wan 视频任务成功但没有 video_url。")
                return str(output["video_url"])
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                raise ProviderException(
                    self.name,
                    f"Wan 视频任务 {status}: {output.get('message') or body.get('message') or '未知错误'}",
                )
            if time.monotonic() >= deadline:
                raise ProviderException(
                    self.name,
                    f"Wan 视频任务等待超时 ({self.generation_timeout}s，task_id={task_id})。",
                )
            await asyncio.sleep(self.poll_interval)

    def _body(self, response: httpx.Response, action: str) -> dict:
        if not response.is_success:
            raise ProviderException(
                self.name,
                f"{action}失败 HTTP {response.status_code}: {redact_sensitive_text(response.text[:500])}",
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderException(self.name, f"{action}返回了无效 JSON。") from exc
        if body.get("code"):
            raise ProviderException(
                self.name,
                f"{action}失败: {redact_sensitive_text(str(body.get('message') or body['code']))}",
            )
        return body
