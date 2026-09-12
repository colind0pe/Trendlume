from __future__ import annotations

import base64
import binascii
import math
import re

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.image.protocol import ImageResult
from src.providers.image.style_presets import apply_image_style_preset


class VolcengineImageProvider:
    """Seedream image generation through the Volcengine Ark REST API."""

    name = "volcengine"
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_MODEL = "doubao-seedream-5-0-260128"
    MIN_PIXELS = 3_686_400

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        watermark: bool = False,
        response_format: str = "url",
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = str(model or self.DEFAULT_MODEL).strip()
        self.timeout = float(timeout)
        self.watermark = bool(watermark)
        self.response_format = response_format if response_format in {"url", "b64_json"} else "url"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @classmethod
    def _target_size(
        cls,
        aspect_ratio: str,
        width: int | None,
        height: int | None,
    ) -> tuple[str, int, int]:
        if not width or not height or width <= 0 or height <= 0:
            width, height = {
                "9:16": (720, 1280),
                "16:9": (1280, 720),
                "1:1": (1024, 1024),
            }.get(aspect_ratio, (1024, 1024))

        width, height = int(width), int(height)
        scale = max(1.0, math.sqrt(cls.MIN_PIXELS / (width * height)))
        width = max(2, int(round(width * scale)) & ~1)
        height = max(2, int(round(height * scale)) & ~1)
        return f"{width}x{height}", width, height

    @staticmethod
    def _parse_size(value: object) -> tuple[int, int] | None:
        if not isinstance(value, str):
            return None
        match = re.search(r"(\d+)\s*[x*×]\s*(\d+)", value)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

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

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        style_preset: str = "cinematic",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> ImageResult:
        del workflow
        if not self.api_key:
            raise ProviderException(self.name, "火山方舟图像生成未配置 API Key。")
        if not prompt or not prompt.strip():
            raise ProviderException(self.name, "图像生成提示词不能为空。")

        prompt = apply_image_style_preset(prompt, style_preset)
        size, target_width, target_height = self._target_size(aspect_ratio, width, height)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "response_format": self.response_format,
            "stream": False,
            "watermark": self.watermark,
            "sequential_image_generation": "disabled",
        }
        url = f"{self.base_url}/images/generations"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(url, json=payload, headers=self._headers())
                if response.status_code < 200 or response.status_code >= 300:
                    raise ProviderException(
                        self.name,
                        f"Seedream 图像请求失败 HTTP {response.status_code}: "
                        f"{redact_sensitive_text(self._error_message(response))}",
                    )

                try:
                    body = response.json()
                except ValueError as exc:
                    raise ProviderException(self.name, "Seedream 返回了无效 JSON。") from exc

                items = body.get("data") if isinstance(body, dict) else None
                item = items[0] if isinstance(items, list) and items else None
                if isinstance(item, str):
                    item = {"url": item}
                if not isinstance(item, dict):
                    raise ProviderException(self.name, "Seedream 返回中没有图像数据。")

                image_bytes: bytes | None = None
                mime_type = "image/png"
                image_format = "png"
                encoded = item.get("b64_json")
                if isinstance(encoded, str) and encoded:
                    try:
                        image_bytes = base64.b64decode(encoded, validate=True)
                    except (ValueError, binascii.Error) as exc:
                        raise ProviderException(self.name, "Seedream 返回的 Base64 图像无效。") from exc
                else:
                    image_url = item.get("url")
                    if not isinstance(image_url, str) or not image_url:
                        raise ProviderException(self.name, "Seedream 返回中没有可下载的图像 URL。")
                    image_response = await client.get(image_url)
                    if image_response.status_code < 200 or image_response.status_code >= 300:
                        raise ProviderException(
                            self.name,
                            f"下载 Seedream 图像失败 HTTP {image_response.status_code}。",
                        )
                    image_bytes = image_response.content
                    content_type = image_response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type.startswith("image/"):
                        mime_type = content_type
                        image_format = content_type.split("/", 1)[1] or image_format

                if not image_bytes:
                    raise ProviderException(self.name, "Seedream 返回空图像。")

                actual_size = self._parse_size(item.get("size"))
                actual_width, actual_height = actual_size or (target_width, target_height)
                logger.info(
                    "Volcengine image generated successfully: model={}, size={}x{}",
                    self.model,
                    actual_width,
                    actual_height,
                )
                return ImageResult(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    width=actual_width,
                    height=actual_height,
                    format=image_format,
                )
        except ProviderException:
            raise
        except httpx.RequestError as exc:
            raise ProviderException(self.name, f"连接火山方舟图像服务失败: {exc}") from exc
        except Exception as exc:
            raise ProviderException(self.name, f"火山方舟图像生成失败: {exc}") from exc
