import base64
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field

from src.api.dependencies import get_provider_manager
from src.providers.image.comfyui_image import (
    DEFAULT_COMFYUI_IMAGE_WORKFLOW,
    ComfyUIImageProvider,
)
from src.providers.image.protocol import DEFAULT_IMAGE_TEST_PROMPT
from src.providers.image.style_presets import DEFAULT_IMAGE_STYLE_PRESET, ImageStylePreset
from src.providers.llm.defaults import DEFAULT_OPENAI_MODEL
from src.providers.tts.edge_tts import EdgeTTSProvider
from src.schemas.common import APIResponse
from src.schemas.provider import (
    ProviderConfigCreate,
    ProviderConfigResponse,
    ProviderConfigUpdate,
    ProviderTestRequest,
    ProviderTestResponse,
)
from src.services.provider_manager import ProviderManager
from src.services.workflow_service import workflow_service

router = APIRouter(prefix="/providers", tags=["Providers"])


# -----------------------------------------------------------------------------
# 1. Static Query & Summary Routes (Must come before /{provider_id})
# -----------------------------------------------------------------------------
@router.get("", response_model=APIResponse[list[ProviderConfigResponse]])
async def list_providers(
    provider_type: str | None = Query(None, alias="type", description="Filter by provider category"),
    manager: ProviderManager = Depends(get_provider_manager),
):
    """List all configured providers in SQLite with masked credentials"""
    providers = await manager.list_providers(provider_type=provider_type)
    return APIResponse(data=providers)


@router.get("/capabilities", response_model=APIResponse[list[dict]])
async def provider_capabilities(
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Return an explicit REAL/MOCK/OFFLINE capability view for the UI and smoke tests."""
    providers = await manager.list_providers()
    summary = await manager.get_system_config_summary()
    summary_by_id = {item["id"]: item for item in summary["providers"]}
    category_by_type = {item["type"]: item for item in summary["categories"]}
    capabilities: list[dict] = []
    for provider in providers:
        provider_summary = summary_by_id.get(provider.id, {})
        category_summary = category_by_type.get(provider.provider_type, {})
        connection_status = provider_summary.get("connection_status", "not_configured")
        configured = bool(provider_summary.get("configured"))
        if provider.provider_type == "publishing":
            configured = bool(category_summary.get("configured"))
            connection_status = category_summary.get("status", connection_status)
        if not provider.enabled:
            mode = "offline"
            health = "disabled"
        elif provider.provider_name == "mock":
            mode = "mock"
            health = "ready"
        elif configured:
            mode = "real"
            health = connection_status
        else:
            mode = "offline"
            health = "not_configured"
        type_capabilities = {
            "llm": ["script_generation"],
            "search": ["topic_research"],
            "tts": ["speech_synthesis", "voice_speed"],
            "image": ["scene_image"],
            "video": ["scene_video"],
            "material": ["online_scene_video"],
            "publishing": ["manual_publish"],
        }.get(provider.provider_type, [])
        capabilities.append(
            {
                "provider": provider.provider_name,
                "provider_type": provider.provider_type,
                "configured": configured,
                "enabled": provider.enabled,
                "mode": mode,
                "health": health,
                "capabilities": type_capabilities,
            }
        )
    return APIResponse(data=capabilities)


@router.get("/summary", response_model=APIResponse[dict])
async def system_config_summary(
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Return the safe aggregate used by the system configuration center."""
    return APIResponse(data=await manager.get_system_config_summary())


@router.get("/voices", response_model=APIResponse[list[dict]])
async def list_voices(
    active: bool = False,
    provider_id: str | None = Query(None, description="指定已保存的 TTS Provider"),
    manager: ProviderManager = Depends(get_provider_manager),
):
    """List the selected provider voices, or the built-in Edge catalog for settings."""
    tts = await manager.get_tts(provider_id) if active or provider_id else EdgeTTSProvider()
    voices = await tts.list_voices()
    return APIResponse(
        data=[
            {
                "id": v.id,
                "name": v.name,
                "gender": v.gender,
                "language": v.language,
                "locale": v.locale,
            }
            for v in voices
        ]
    )


class TTSVoiceTestRequest(BaseModel):
    provider_id: str | None = None
    voice_id: str | None = None
    text: str = "你好，这是 Trendlume 神经网络语音合成试听测试。"
    speed_ratio: float | None = Field(default=None, ge=0.5, le=2.0)


@router.post("/voices/test")
async def test_tts_voice(
    payload: TTSVoiceTestRequest,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Synthesize and stream test audio from the selected active provider."""
    tts = await manager.get_tts(payload.provider_id)
    text = payload.text or "你好，这是 Trendlume 神经网络语音合成试听测试。"
    if payload.speed_ratio is None:
        res = await tts.synthesize(text, voice_id=payload.voice_id)
    else:
        res = await tts.synthesize(text, voice_id=payload.voice_id, speed=payload.speed_ratio)
    return Response(
        content=res.audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"inline; filename=test_{payload.voice_id or 'default'}.mp3",
            "X-Duration-Seconds": str(res.duration_seconds),
        },
    )


@router.get("/comfyui/workflows", response_model=APIResponse[list[dict]])
async def list_comfyui_workflows(
    type: str | None = Query(None, description="Filter workflows by category (image, video, audio, analysis)"),
):
    """Scan and list all available ComfyUI workflows dynamically grouped by subfolder"""
    items = workflow_service.scan_workflows(category=type)
    return APIResponse(data=items)


class ComfyUITestRequest(BaseModel):
    base_url: str = "http://127.0.0.1:8188"
    api_key: str | None = None


@router.post("/comfyui/test", response_model=APIResponse[dict])
async def test_comfyui_connection(
    payload: ComfyUITestRequest,
    manager: ProviderManager = Depends(get_provider_manager),
):
    req = ProviderTestRequest(
        provider_type="image",
        provider_name="comfyui",
        config={"base_url": payload.base_url},
        credentials={"api_key": payload.api_key} if payload.api_key else None,
    )
    res = await manager.test_provider(req)
    return APIResponse(data={"connected": res.connected, "message": res.message})


class ComfyUIGenerateTestRequest(BaseModel):
    prompt: str = DEFAULT_IMAGE_TEST_PROMPT
    workflow: str | None = None
    base_url: str = "http://127.0.0.1:8188"
    api_key: str | None = None


@router.post("/comfyui/test-generate", response_model=APIResponse[dict])
async def test_comfyui_generate(payload: ComfyUIGenerateTestRequest):
    """Execute test image generation using specified ComfyUI workflow"""
    provider = ComfyUIImageProvider(
        base_url=payload.base_url or "http://127.0.0.1:8188",
        api_key=payload.api_key,
        default_workflow=payload.workflow or DEFAULT_COMFYUI_IMAGE_WORKFLOW,
        timeout=120.0,
    )
    res = await provider.generate_image(
        prompt=payload.prompt or DEFAULT_IMAGE_TEST_PROMPT,
        aspect_ratio="16:9",
        workflow=payload.workflow,
    )
    b64_data = base64.b64encode(res.image_bytes).decode("utf-8")
    data_url = f"data:{res.mime_type};base64,{b64_data}"
    return APIResponse(
        data={
            "image_url": data_url,
            "width": res.width,
            "height": res.height,
            "format": res.format,
            "message": "ComfyUI 测试图像生成成功！",
        }
    )


class ImageGenerationTestRequest(BaseModel):
    """Payload for a provider-aware image generation smoke test."""

    provider_id: str | None = None
    provider_name: str | None = None
    config: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    prompt: str = Field(default=DEFAULT_IMAGE_TEST_PROMPT, min_length=1, max_length=500)
    aspect_ratio: Literal["1:1", "16:9", "9:16"] = "16:9"
    style_preset: ImageStylePreset = DEFAULT_IMAGE_STYLE_PRESET


@router.post("/image/test-generate", response_model=APIResponse[dict])
async def test_image_generation(
    payload: ImageGenerationTestRequest,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Generate one in-memory image with the current image Provider configuration."""
    res = await manager.test_provider(
        ProviderTestRequest(
            provider_id=payload.provider_id,
            provider_type="image",
            provider_name=payload.provider_name,
            config=payload.config,
            credentials=payload.credentials,
            test_payload={
                "operation": "generate",
                "prompt": payload.prompt.strip() or DEFAULT_IMAGE_TEST_PROMPT,
                "aspect_ratio": payload.aspect_ratio,
                "style_preset": payload.style_preset,
            },
        )
    )
    return APIResponse(
        data={
            "connected": res.connected,
            "message": res.message,
            "latency_ms": res.latency_ms,
            **(res.details or {}),
        }
    )


class LLMTestRequest(BaseModel):
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    model: str = DEFAULT_OPENAI_MODEL


@router.post("/llm/test", response_model=APIResponse[dict])
async def test_llm_shortcut(
    payload: LLMTestRequest,
    manager: ProviderManager = Depends(get_provider_manager),
):
    req = ProviderTestRequest(
        provider_type="llm",
        config={"base_url": payload.base_url, "model": payload.model},
        credentials={"api_key": payload.api_key} if payload.api_key else None,
    )
    res = await manager.test_provider(req)
    return APIResponse(
        data={
            "connected": res.connected,
            "message": res.message,
            "latency_ms": res.latency_ms,
            "model": payload.model,
            "reply": (res.details or {}).get("reply", ""),
        }
    )


class TavilyTestRequest(BaseModel):
    api_key: str | None = None
    query: str = "Trendlume"


@router.post("/search/test", response_model=APIResponse[dict])
async def test_search_shortcut(
    payload: TavilyTestRequest,
    manager: ProviderManager = Depends(get_provider_manager),
):
    req = ProviderTestRequest(
        provider_type="search",
        provider_name="tavily",
        credentials={"api_key": payload.api_key} if payload.api_key else None,
        test_payload={"query": payload.query},
    )
    res = await manager.test_provider(req)
    return APIResponse(
        data={
            "connected": res.connected,
            "message": res.message,
            "latency_ms": res.latency_ms,
            "results_count": (res.details or {}).get("results_count", 0),
        }
    )


@router.post("/test", response_model=APIResponse[ProviderTestResponse])
async def test_provider_connection(
    payload: ProviderTestRequest,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Test connection with specified or in-flight provider configuration"""
    res = await manager.test_provider(payload)
    return APIResponse(data=res)


# -----------------------------------------------------------------------------
# 2. Parameterized Routes (/{provider_id})
# -----------------------------------------------------------------------------
@router.post("", response_model=APIResponse[ProviderConfigResponse], status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderConfigCreate,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Create a new provider configuration with encrypted credentials"""
    created = await manager.create_provider(payload)
    return APIResponse(data=created)


@router.get("/{provider_id}", response_model=APIResponse[ProviderConfigResponse])
async def get_provider_detail(
    provider_id: str,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Get single provider configuration detail with masked credentials"""
    detail = await manager.get_provider(provider_id)
    return APIResponse(data=detail)


@router.put("/{provider_id}", response_model=APIResponse[ProviderConfigResponse])
async def update_provider(
    provider_id: str,
    payload: ProviderConfigUpdate,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Update an existing provider configuration (smartly preserving masked credentials)"""
    updated = await manager.update_provider(provider_id, payload)
    return APIResponse(data=updated)


@router.delete("/{provider_id}", response_model=APIResponse[bool])
async def delete_provider(
    provider_id: str,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Delete a provider configuration and its encrypted credentials"""
    success = await manager.delete_provider(provider_id)
    return APIResponse(data=success)


@router.post("/{provider_id}/set-default", response_model=APIResponse[ProviderConfigResponse])
async def set_default_provider(
    provider_id: str,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Set a provider as the default primary provider for its category"""
    updated = await manager.set_default_provider(provider_id)
    return APIResponse(data=updated)


@router.post("/{provider_id}/toggle", response_model=APIResponse[ProviderConfigResponse])
async def toggle_provider_enabled(
    provider_id: str,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Toggle enabled/disabled state of a provider"""
    updated = await manager.toggle_provider(provider_id)
    return APIResponse(data=updated)


@router.post("/{provider_id}/test", response_model=APIResponse[ProviderTestResponse])
async def test_provider_by_id(
    provider_id: str,
    manager: ProviderManager = Depends(get_provider_manager),
):
    """Test connection for a specific saved provider ID"""
    res = await manager.test_provider(ProviderTestRequest(provider_id=provider_id))
    return APIResponse(data=res)
