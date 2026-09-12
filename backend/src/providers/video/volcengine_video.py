from __future__ import annotations

import asyncio
import base64
import mimetypes
import time
from pathlib import Path

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.video.protocol import VideoResult


class VolcengineVideoProvider:
    """Seedance video generation through the Volcengine Ark task API."""

    name = "volcengine"
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_MODEL = "doubao-seedance-2-0-260128"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        generation_timeout: float = 1800.0,
        poll_interval: float = 5.0,
        resolution: str = "720p",
        watermark: bool = False,
        generate_audio: bool = False,
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = str(model or self.DEFAULT_MODEL).strip()
        self.timeout = float(timeout)
        self.generation_timeout = float(generation_timeout)
        self.poll_interval = max(0.5, float(poll_interval))
        self.resolution = str(resolution or "720p")
        self.watermark = bool(watermark)
        self.generate_audio = bool(generate_audio)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _image_reference(image_url: str) -> str:
        if image_url.startswith(("http://", "https://", "data:")):
            return image_url
        path = Path(image_url)
        if not path.is_file():
            raise ProviderException("volcengine", f"首帧图片不存在: {image_url}")
        content_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text[:500]
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            return str(payload.get("message") or payload.get("detail") or payload)
        return str(payload)

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
        del workflow
        if not self.api_key:
            raise ProviderException(self.name, "火山方舟视频生成未配置 API Key。")
        if not prompt or not prompt.strip():
            raise ProviderException(self.name, "视频生成提示词不能为空。")

        content: list[dict] = [{"type": "text", "text": prompt}]
        if image_url:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_reference(image_url)},
                    "role": "first_frame",
                }
            )

        duration = max(1, int(round(float(duration_seconds or 4.0))))
        payload = {
            "model": self.model,
            "content": content,
            "duration": duration,
            "ratio": aspect_ratio if aspect_ratio in {"9:16", "16:9", "1:1"} else "adaptive",
            "resolution": self.resolution,
            "watermark": self.watermark,
            "generate_audio": self.generate_audio,
        }
        create_url = f"{self.base_url}/contents/generations/tasks"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                create_response = await client.post(
                    create_url,
                    json=payload,
                    headers=self._headers(),
                )
                if create_response.status_code < 200 or create_response.status_code >= 300:
                    raise ProviderException(
                        self.name,
                        f"Seedance 任务创建失败 HTTP {create_response.status_code}: "
                        f"{redact_sensitive_text(self._error_message(create_response))}",
                    )
                try:
                    create_body = create_response.json()
                except ValueError as exc:
                    raise ProviderException(self.name, "Seedance 创建接口返回了无效 JSON。") from exc

                task_id = create_body.get("id") or create_body.get("task_id")
                if not task_id:
                    raise ProviderException(self.name, "Seedance 返回中没有任务 ID。")

                video_url = await self._poll_task(client, str(task_id))
                # The task API returns a signed CDN URL.  Do not forward the
                # Ark Bearer token to that unrelated host.
                download_response = await client.get(video_url)
                if download_response.status_code < 200 or download_response.status_code >= 300:
                    raise ProviderException(
                        self.name,
                        f"下载 Seedance 视频失败 HTTP {download_response.status_code}。",
                    )
                video_bytes = download_response.content
                if not video_bytes:
                    raise ProviderException(self.name, "Seedance 返回空视频。")

                if width and height and width > 0 and height > 0:
                    output_width, output_height = int(width), int(height)
                else:
                    output_width, output_height = {
                        "9:16": (720, 1280),
                        "16:9": (1280, 720),
                        "1:1": (1024, 1024),
                    }.get(aspect_ratio, (720, 1280))
                logger.info("Volcengine video generated successfully: task_id={}", task_id)
                return VideoResult(
                    video_bytes=video_bytes,
                    duration_seconds=float(duration),
                    width=output_width,
                    height=output_height,
                    format="mp4",
                    mime_type="video/mp4",
                )
        except ProviderException:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderException(
                self.name,
                f"连接火山方舟视频服务超时（单次请求 {self.timeout}s）: {exc}",
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderException(self.name, f"连接火山方舟视频服务失败: {exc}") from exc
        except Exception as exc:
            raise ProviderException(self.name, f"火山方舟视频生成失败: {exc}") from exc

    async def _poll_task(self, client: httpx.AsyncClient, task_id: str) -> str:
        query_url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        deadline = time.monotonic() + self.generation_timeout
        while True:
            response = await client.get(query_url, headers=self._headers())
            if response.status_code < 200 or response.status_code >= 300:
                raise ProviderException(
                    self.name,
                    f"Seedance 查询任务失败 HTTP {response.status_code}: "
                    f"{redact_sensitive_text(self._error_message(response))}",
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise ProviderException(self.name, "Seedance 查询接口返回了无效 JSON。") from exc

            status = str(body.get("status") or "").lower()
            if status == "succeeded":
                content = body.get("content")
                video_url = content.get("video_url") if isinstance(content, dict) else None
                video_url = video_url or body.get("video_url")
                if not video_url:
                    raise ProviderException(self.name, "Seedance 任务成功但没有视频 URL。")
                return str(video_url)
            if status in {"failed", "expired", "cancelled"}:
                error = body.get("error") or {}
                message = error.get("message") if isinstance(error, dict) else error
                raise ProviderException(
                    self.name,
                    f"Seedance 任务 {status}: {message or body.get('status_msg') or '未知错误'}",
                )
            if time.monotonic() >= deadline:
                raise ProviderException(
                    self.name,
                    f"Seedance 任务等待超时 ({self.generation_timeout}s，task_id={task_id})。",
                )
            await asyncio.sleep(self.poll_interval)
