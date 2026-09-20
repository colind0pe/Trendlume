from __future__ import annotations

import base64
import binascii

import httpx

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.image.protocol import ImageResult
from src.providers.image.style_presets import apply_image_style_preset
from src.providers.media_utils import local_media_data, output_dimensions


class GoogleImageProvider:
    """Gemini native image generation and multi-reference editing."""

    name = "google"
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1"
    DEFAULT_MODEL = "gemini-3.1-flash-image"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 600.0,
        image_size: str = "1K",
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = str(model or self.DEFAULT_MODEL).strip()
        self.timeout = float(timeout)
        self.image_size = str(image_size or "1K").upper()

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        style_preset: str = "cinematic",
        workflow: str | None = None,
        width: int | None = None,
        height: int | None = None,
        reference_image_path: str | None = None,
        reference_image_paths: list[str] | None = None,
        continuity_input: dict | None = None,
    ) -> ImageResult:
        del workflow, continuity_input
        if not self.api_key:
            raise ProviderException(self.name, "Google Gemini 未配置 API Key。")
        if not str(prompt or "").strip():
            raise ProviderException(self.name, "图像生成提示词不能为空。")

        references = list(reference_image_paths or [])
        if reference_image_path and reference_image_path not in references:
            references.insert(0, reference_image_path)
        if len(references) > 14:
            raise ProviderException(self.name, "Gemini 最多支持 14 张参考图。")
        parts: list[dict] = []
        for item in references:
            mime_type, encoded = local_media_data(item, self.name)
            parts.append({"inlineData": {"mimeType": mime_type, "data": encoded}})
        parts.append({"text": apply_image_style_preset(prompt, style_preset)})
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "responseFormat": {
                    "image": {"aspectRatio": aspect_ratio, "imageSize": self.image_size}
                },
            },
        }
        target_width, target_height = output_dimensions(aspect_ratio, width, height)
        url = f"{self.base_url}/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(
                    url, headers={"x-goog-api-key": self.api_key}, json=payload
                )
                if not response.is_success:
                    raise ProviderException(
                        self.name,
                        f"Gemini Image 请求失败 HTTP {response.status_code}: "
                        f"{redact_sensitive_text(response.text[:500])}",
                    )
                body = response.json()
                candidates = body.get("candidates") or []
                result_parts = (
                    ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
                )
                inline = next(
                    (item.get("inlineData") for item in result_parts if item.get("inlineData")),
                    None,
                )
                if not inline or not inline.get("data"):
                    raise ProviderException(self.name, "Gemini Image 返回中没有图像数据。")
                try:
                    image_bytes = base64.b64decode(inline["data"], validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ProviderException(
                        self.name, "Gemini Image 返回的 Base64 图像无效。"
                    ) from exc
                mime_type = str(inline.get("mimeType") or "image/png")
                return ImageResult(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    width=target_width,
                    height=target_height,
                    format=(
                        mime_type.split("/", 1)[1] if mime_type.startswith("image/") else "png"
                    ),
                )
        except ProviderException:
            raise
        except (httpx.RequestError, ValueError) as exc:
            raise ProviderException(self.name, f"Google Gemini 图像生成失败: {exc}") from exc
