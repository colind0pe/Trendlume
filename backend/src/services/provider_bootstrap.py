from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import secret_cipher
from src.models.provider_config import ProviderConfigModel
from src.providers.image.comfyui_image import DEFAULT_COMFYUI_IMAGE_WORKFLOW
from src.providers.llm.defaults import default_llm_model


async def bootstrap_default_providers(session: AsyncSession) -> bool:
    """Bootstrap default provider configurations into SQLite once during initial setup.

    Ensures that existing .env keys (if any) are migrated once, and that out-of-the-box
    defaults (like Edge-TTS, ComfyUI, DeepSeek presets) are seeded.
    Once seeded, SQLite is the single source of truth and .env is never re-read for providers.
    If user deletes all providers, they will NOT be re-seeded on next restart because
    the internal system sentinel record persists in SQLite.
    """
    stmt = select(ProviderConfigModel).where(ProviderConfigModel.id == "sys_bootstrap_done")
    res = await session.execute(stmt)
    if res.scalar_one_or_none() is not None:
        return False  # Already initialized previously

    stmt_any = select(ProviderConfigModel).limit(1)
    res_any = await session.execute(stmt_any)
    if res_any.scalar_one_or_none() is not None:
        session.add(
            ProviderConfigModel(
                id="sys_bootstrap_done",
                provider_type="system",
                provider_name="bootstrap",
                display_name="System Bootstrap Sentinel",
                enabled=False,
                is_default=False,
                config={"version": 1},
            )
        )
        await session.commit()
        return False

    logger.info("Initializing SQLite provider_configs table with default presets and .env migration...")

    # 1. LLM Defaults & .env Migration
    llm_key = getattr(settings, "openai_api_key", None)
    custom_key = getattr(settings, "custom_api_key", None)
    llm_base = getattr(settings, "openai_base_url", None)
    llm_model = getattr(settings, "openai_model", None)
    configured_active_llm = str(getattr(settings, "active_llm_provider", None) or "").strip().lower()
    base_hint = str(llm_base or "").strip().lower()
    if configured_active_llm:
        active_llm_id = configured_active_llm
    elif "deepseek" in base_hint:
        active_llm_id = "deepseek"
    elif "anthropic" in base_hint or "claude" in base_hint:
        active_llm_id = "claude"
    elif "cloudflare" in base_hint:
        active_llm_id = "cloudflare"
    elif "ollama" in base_hint or "11434" in base_hint:
        active_llm_id = "ollama"
    elif "openai.com" in base_hint:
        active_llm_id = "openai"
    elif llm_base:
        active_llm_id = "custom"
    elif getattr(settings, "deepseek_api_key", None):
        active_llm_id = "deepseek"
    elif getattr(settings, "claude_api_key", None):
        active_llm_id = "claude"
    elif getattr(settings, "cloudflare_api_key", None):
        active_llm_id = "cloudflare"
    elif llm_key:
        active_llm_id = "openai"
    else:
        active_llm_id = "deepseek"

    # Preset templates for LLM
    llm_presets = [
        {
            "id": "prov_llm_deepseek",
            "name": "deepseek",
            "display": "DeepSeek (深度求索)",
            "base_url": "https://api.deepseek.com",
            "model": default_llm_model("deepseek"),
            "key": getattr(settings, "deepseek_api_key", None) or (llm_key if "deepseek" in base_hint else None),
            "is_default": active_llm_id == "deepseek",
        },
        {
            "id": "prov_llm_openai",
            "name": "openai",
            "display": "OpenAI GPT-5.6 Luna",
            "base_url": "https://api.openai.com/v1",
            "model": default_llm_model("openai"),
            "key": (llm_key if "openai.com" in base_hint else None),
            "is_default": active_llm_id == "openai",
        },
        {
            "id": "prov_llm_claude",
            "name": "claude",
            "display": "Anthropic Claude Sonnet 5",
            "base_url": "https://api.anthropic.com/v1",
            "model": default_llm_model("claude"),
            "key": getattr(settings, "claude_api_key", None)
            or (llm_key if "anthropic" in base_hint else None),
            "is_default": active_llm_id in {"claude", "anthropic"},
        },
        {
            "id": "prov_llm_cloudflare",
            "name": "cloudflare",
            "display": "Cloudflare Workers AI",
            "base_url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
            "model": default_llm_model("cloudflare"),
            "key": getattr(settings, "cloudflare_api_key", None) or (llm_key if "cloudflare" in base_hint else None),
            "is_default": active_llm_id == "cloudflare",
        },
        {
            "id": "prov_llm_ollama",
            "name": "ollama",
            "display": "Ollama (本地私有化部署)",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": default_llm_model("ollama"),
            "key": None,
            "is_default": active_llm_id == "ollama",
        },
    ]

    # If current .env has custom base_url/model not in presets, create a custom provider
    if llm_base and not any(p["base_url"] in llm_base for p in llm_presets):
        llm_presets.append({
            "id": "prov_llm_custom",
            "name": "custom",
            "display": "自定义 OpenAI 兼容模型",
            "base_url": llm_base,
            "model": llm_model or "",
            "key": custom_key or llm_key,
            "is_default": active_llm_id == "custom",
        })

    for p in llm_presets:
        creds = {"api_key": p["key"]} if p["key"] else {}
        session.add(
            ProviderConfigModel(
                id=p["id"],
                provider_type="llm",
                provider_name=p["name"],
                display_name=p["display"],
                enabled=True,
                is_default=p["is_default"],
                config={
                    "base_url": p["base_url"],
                    "model": p["model"],
                    "temperature": 0.7,
                    "max_tokens": 2000,
                },
                credentials_encrypted=secret_cipher.encrypt_dict(creds) if creds else None,
            )
        )

    # 2. Search Default (Tavily)
    tavily_key = getattr(settings, "tavily_api_key", None)
    tavily_creds = {"api_key": tavily_key} if tavily_key else {}
    session.add(
        ProviderConfigModel(
            id="prov_search_tavily",
            provider_type="search",
            provider_name="tavily",
            display_name="Tavily 全网实时深度检索",
            enabled=True,
            is_default=True,
            config={
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
            },
            credentials_encrypted=secret_cipher.encrypt_dict(tavily_creds) if tavily_creds else None,
        )
    )

    # 3. Optional online stock-video materials (Pexels).  The category is
    # intentionally optional: missing credentials must not make image/video
    # generation unavailable.
    pexels_key = getattr(settings, "pexels_api_key", None)
    session.add(
        ProviderConfigModel(
            id="prov_material_pexels",
            provider_type="material",
            provider_name="pexels",
            display_name="Pexels 在线视频素材",
            enabled=True,
            is_default=True,
            config={
                "locale": "zh-CN",
                "size": "medium",
                "min_short_edge": 720,
                "timeout": 15.0,
                "download_timeout": 120.0,
                "max_download_bytes": 200 * 1024 * 1024,
            },
            credentials_encrypted=secret_cipher.encrypt_dict({"api_key": pexels_key}) if pexels_key else None,
        )
    )

    # 4. TTS Default (Edge-TTS zero-cost)
    session.add(
        ProviderConfigModel(
            id="prov_tts_edge",
            provider_type="tts",
            provider_name="edge_tts",
            display_name="微软 Edge-TTS 神经网络语音 (内置免费)",
            enabled=True,
            is_default=True,
            config={
                "default_voice": "zh-CN-YunxiNeural",
                "rate": "+0%",
                "volume": "+0%",
            },
            credentials_encrypted=None,
        )
    )

    # 4. Image Default (ComfyUI)
    comfy_url = getattr(settings, "comfyui_base_url", None) or "http://127.0.0.1:8188"
    comfy_key = getattr(settings, "comfyui_api_key", None)
    comfy_creds = {"api_key": comfy_key} if comfy_key else {}
    comfy_img_wf = getattr(settings, "comfyui_image_workflow", None) or DEFAULT_COMFYUI_IMAGE_WORKFLOW
    session.add(
        ProviderConfigModel(
            id="prov_image_comfyui",
            provider_type="image",
            provider_name="comfyui",
            display_name="本地 ComfyUI 高清分镜画面渲染",
            enabled=True,
            is_default=True,
            config={
                "base_url": comfy_url,
                "default_workflow": comfy_img_wf,
                "timeout": 120.0,
            },
            credentials_encrypted=secret_cipher.encrypt_dict(comfy_creds) if comfy_creds else None,
        )
    )

    # 5. Video Default (ComfyUI)
    comfy_vid_wf = getattr(settings, "comfyui_video_workflow", "video/video_wan2.1_fusionx.json")
    session.add(
        ProviderConfigModel(
            id="prov_video_comfyui",
            provider_type="video",
            provider_name="comfyui",
            display_name="本地 ComfyUI 动态视频生成",
            enabled=True,
            is_default=True,
            config={
                "base_url": comfy_url,
                "default_workflow": comfy_vid_wf,
                "timeout": 300.0,
            },
            credentials_encrypted=secret_cipher.encrypt_dict(comfy_creds) if comfy_creds else None,
        )
    )

    # 6. Publishing Default (Douyin)
    session.add(
        ProviderConfigModel(
            id="prov_pub_douyin",
            provider_type="publishing",
            provider_name="douyin",
            display_name="抖音开放平台 (Douyin Open Platform)",
            enabled=True,
            is_default=True,
            config={
                "platform": "douyin",
                "default_tags": ["Trendlume", "AI视频", "科普"],
            },
            credentials_encrypted=None,
        )
    )

    # 7. Internal System Bootstrap Sentinel (Prevents re-seeding if user deletes all providers)
    session.add(
        ProviderConfigModel(
            id="sys_bootstrap_done",
            provider_type="system",
            provider_name="bootstrap",
            display_name="System Bootstrap Sentinel",
            enabled=False,
            is_default=False,
            config={"version": 1},
        )
    )

    await session.commit()
    logger.info("Successfully bootstrapped default provider configurations into SQLite.")
    return True
