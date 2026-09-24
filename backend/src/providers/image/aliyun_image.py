from __future__ import annotations

import httpx

from src.core.exceptions import ProviderException
from src.core.security import redact_sensitive_text
from src.providers.image.protocol import ImageResult
from src.providers.image.style_presets import apply_image_style_preset
from src.providers.media_utils import media_data_url, output_dimensions


class AliyunImageProvider:
    """Qwen Image 3.0 through Alibaba Cloud Model Studio."""

    name = "aliyun"
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
    DEFAULT_MODEL = "qwen-image-3.0-pro"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 600.0,
        prompt_extend: bool = True,
        watermark: bool = False,
    ):
        self.api_key = str(api_key or "").strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.model = str(model or self.DEFAULT_MODEL).strip()
        self.timeout = float(timeout)
        self.prompt_extend = bool(prompt_extend)
        self.watermark = bool(watermark)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

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
            raise ProviderException(self.name, "阿里云百炼未配置 API Key。")
        if not str(prompt or "").strip():
            raise ProviderException(self.name, "图像生成提示词不能为空。")

        references = list(reference_image_paths or [])
        if reference_image_path and reference_image_path not in references:
            references.insert(0, reference_image_path)
        if len(references) > 3:
            raise ProviderException(self.name, "Qwen Image 3.0 最多支持 3 张参考图。")

        target_width, target_height = output_dimensions(aspect_ratio, width, height)
        content = [{"image": media_data_url(item, self.name)} for item in references]
        content.append({"text": apply_image_style_preset(prompt, style_preset)})
        payload = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {
                "prompt_extend": self.prompt_extend,
                "size": f"{target_width}*{target_height}",
                "watermark": self.watermark,
                "n": 1,
            },
        }
        url = f"{self.base_url}/services/aigc/multimodal-generation/generation"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                if not response.is_success:
                    raise ProviderException(
                        self.name,
                        f"Qwen Image 请求失败 HTTP {response.status_code}: "
                        f"{redact_sensitive_text(response.text[:500])}",
                    )
                body = response.json()
                choices = (body.get("output") or {}).get("choices") or []
                message = choices[0].get("message") if choices else None
                items = message.get("content") if isinstance(message, dict) else None
                image_url = next(
                    (
                        item.get("image")
                        for item in items or []
                        if isinstance(item, dict) and item.get("image")
                    ),
                    None,
                )
                if not image_url:
                    raise ProviderException(self.name, "Qwen Image 返回中没有图像 URL。")
                download = await client.get(str(image_url))
                if not download.is_success or not download.content:
                    raise ProviderException(
                        self.name, f"下载 Qwen Image 图像失败 HTTP {download.status_code}。"
                    )
                usage = body.get("usage") or {}
                mime_type = download.headers.get("content-type", "image/png").split(";", 1)[0]
                if not mime_type.startswith("image/"):
                    mime_type = "image/png"
                return ImageResult(
                    image_bytes=download.content,
                    mime_type=mime_type,
                    width=int(usage.get("output_width") or target_width),
                    height=int(usage.get("output_height") or target_height),
                    format=(
                        mime_type.split("/", 1)[1] if mime_type.startswith("image/") else "png"
                    ),
                )
        except ProviderException:
            raise
        except (httpx.RequestError, ValueError) as exc:
            raise ProviderException(self.name, f"阿里云百炼图像生成失败: {exc}") from exc
