from loguru import logger

from src.core.config import settings
from src.core.exceptions import ValidationException
from src.providers.image.comfyui_image import (
    DEFAULT_COMFYUI_IMAGE_WORKFLOW,
    ComfyUIImageProvider,
)
from src.providers.image.protocol import ImageProvider
from src.providers.llm.defaults import DEFAULT_OPENAI_MODEL
from src.providers.llm.openai_client import OpenAICompatibleLLMProvider, infer_provider_name
from src.providers.llm.protocol import LLMProvider
from src.providers.search.protocol import SearchProvider
from src.providers.search.tavily import TavilySearchProvider
from src.providers.tts.edge_tts import EdgeTTSProvider
from src.providers.tts.protocol import TTSProvider
from src.providers.video.comfyui_video import ComfyUIVideoProvider
from src.providers.video.protocol import VideoProvider


class ProviderRegistry:
    """In-memory provider bootstrap for offline and test fallback paths."""

    def __init__(self):
        self._search_provider: SearchProvider | None = None
        self._llm_provider: LLMProvider | None = None
        self._tts_provider: TTSProvider | None = None
        self._image_provider: ImageProvider | None = None
        self._video_provider: VideoProvider | None = None
        self.reload_from_config()

    def reload_from_config(
        self,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        openai_model: str | None = None,
        comfyui_base_url: str | None = None,
        comfyui_api_key: str | None = None,
        comfyui_image_workflow: str | None = None,
        comfyui_video_workflow: str | None = None,
        tavily_api_key: str | None = None,
        openai_provider_name: str | None = None,
    ) -> None:
        """Instantiate active providers based on current settings. Unconfigured providers remain None."""
        # 1. Search Provider (Tavily if key given, otherwise None)
        if tavily_api_key is not None:
            tavily_key = tavily_api_key.strip() if tavily_api_key.strip() else None
        else:
            tavily_key = getattr(settings, "tavily_api_key", None) or (
                getattr(self._search_provider, "api_key", None) if self._search_provider else None
            )

        if tavily_key and str(tavily_key).strip():
            self._search_provider = TavilySearchProvider(api_key=str(tavily_key).strip())
        else:
            self._search_provider = None

        # 2. LLM Provider (OpenAI, DeepSeek, Qwen, Ollama, Claude, Cloudflare, etc.)
        if openai_api_key is not None:
            llm_key = openai_api_key.strip() if openai_api_key.strip() else None
        else:
            llm_key = getattr(settings, "openai_api_key", None) or (
                getattr(self._llm_provider, "api_key", None) if self._llm_provider else None
            )

        if openai_base_url is not None:
            llm_base = openai_base_url.strip() if openai_base_url.strip() else "https://api.openai.com/v1"
        else:
            llm_base = getattr(settings, "openai_base_url", None) or (
                getattr(self._llm_provider, "base_url", None) if self._llm_provider else "https://api.openai.com/v1"
            )

        if openai_model is not None:
            llm_model = openai_model.strip() if openai_model.strip() else DEFAULT_OPENAI_MODEL
        else:
            llm_model = getattr(settings, "openai_model", None) or (
                getattr(self._llm_provider, "model", None) if self._llm_provider else DEFAULT_OPENAI_MODEL
            )

        configured_provider_name = (openai_provider_name or "").strip()
        if not configured_provider_name:
            configured_provider_name = (
                getattr(settings, "active_llm_provider", None) or ""
            ).strip()
        if not configured_provider_name:
            configured_provider_name = (
                getattr(self._llm_provider, "provider_name", None) or ""
            ).strip()
        llm_provider_name = infer_provider_name(
            configured_provider_name or None,
            str(llm_base),
            str(llm_model),
        )

        if llm_key and str(llm_key).strip():
            self._llm_provider = OpenAICompatibleLLMProvider(
                api_key=str(llm_key).strip(),
                base_url=str(llm_base).strip(),
                model=str(llm_model).strip(),
                provider_name=llm_provider_name,
            )
        else:
            self._llm_provider = None

        # 3. TTS Provider (Default zero-cost Microsoft EdgeTTS)
        self._tts_provider = EdgeTTSProvider()

        # 4. Image & Video Provider (local ComfyUI fallback)
        if comfyui_base_url is not None:
            comfy_url = comfyui_base_url.strip() if comfyui_base_url.strip() else None
        else:
            comfy_url = getattr(settings, "comfyui_base_url", None) or (
                getattr(self._image_provider, "base_url", None) if isinstance(self._image_provider, ComfyUIImageProvider) else None
            )

        if comfyui_api_key is not None:
            comfy_key = comfyui_api_key.strip() if comfyui_api_key.strip() else None
        else:
            comfy_key = getattr(settings, "comfyui_api_key", None) or (
                getattr(self._image_provider, "api_key", None) if isinstance(self._image_provider, ComfyUIImageProvider) else None
            )

        comfy_img_wf = (
            comfyui_image_workflow
            or getattr(settings, "comfyui_image_workflow", None)
            or DEFAULT_COMFYUI_IMAGE_WORKFLOW
        )
        comfy_vid_wf = comfyui_video_workflow or getattr(
            settings, "comfyui_video_workflow", "video/video_wan2.1_fusionx.json"
        )

        if comfy_url:
            self._image_provider = ComfyUIImageProvider(
                base_url=comfy_url,
                api_key=comfy_key,
                default_workflow=comfy_img_wf,
            )
            self._video_provider = ComfyUIVideoProvider(
                base_url=comfy_url,
                api_key=comfy_key,
                default_workflow=comfy_vid_wf,
            )
        else:
            self._image_provider = None
            self._video_provider = None

        logger.info(
            f"ProviderRegistry reloaded: "
            f"Search={self._search_provider.name if self._search_provider else 'UNCONFIGURED (Optional)'}, "
            f"LLM={self._llm_provider.name if self._llm_provider else 'UNCONFIGURED'}, "
            f"TTS={self._tts_provider.name if self._tts_provider else 'None'}, "
            f"Image={self._image_provider.name if self._image_provider else 'UNCONFIGURED'}, "
            f"Video={self._video_provider.name if self._video_provider else 'UNCONFIGURED'}"
        )

    @property
    def is_search_configured(self) -> bool:
        return self._search_provider is not None

    @property
    def is_llm_configured(self) -> bool:
        return self._llm_provider is not None

    @property
    def is_tts_configured(self) -> bool:
        return self._tts_provider is not None

    @property
    def is_image_configured(self) -> bool:
        return self._image_provider is not None

    @property
    def is_video_configured(self) -> bool:
        return self._video_provider is not None

    @property
    def search(self) -> SearchProvider:
        if not self._search_provider:
            raise ValidationException("未配置 Tavily 检索密钥，实时全网检索功能当前未启用。")
        return self._search_provider

    @property
    def llm(self) -> LLMProvider:
        if not self._llm_provider:
            raise ValidationException(
                "未配置大语言模型 API Key，无法进行剧本分镜创作。请前往【设置中心】填写 OpenAI / DeepSeek / Claude / Cloudflare / Ollama API 凭证。"
            )
        return self._llm_provider

    @property
    def tts(self) -> TTSProvider:
        if not self._tts_provider:
            self._tts_provider = EdgeTTSProvider()
        return self._tts_provider

    @property
    def image(self) -> ImageProvider:
        if not self._image_provider:
            raise ValidationException(
                "未配置文生图服务，无法生成分镜画面。请前往【设置中心】配置本地 ComfyUI 或火山方舟。"
            )
        return self._image_provider

    @property
    def video(self) -> VideoProvider:
        if not self._video_provider:
            raise ValidationException(
                "未配置文生视频服务，无法生成动态视频。请前往【设置中心】配置本地 ComfyUI 地址 (如 http://127.0.0.1:8188)。"
            )
        return self._video_provider

provider_registry = ProviderRegistry()
