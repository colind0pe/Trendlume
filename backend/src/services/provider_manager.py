import base64
import copy
import time
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import NotFoundException, ProviderException, ValidationException
from src.core.security import redact_sensitive_text, secret_cipher
from src.models.provider_config import ProviderConfigModel
from src.providers.image.comfyui_image import (
    DEFAULT_COMFYUI_IMAGE_WORKFLOW,
    ComfyUIImageProvider,
)
from src.providers.image.protocol import DEFAULT_IMAGE_TEST_PROMPT, ImageProvider
from src.providers.image.style_presets import DEFAULT_IMAGE_STYLE_PRESET
from src.providers.image.volcengine_image import VolcengineImageProvider
from src.providers.llm.anthropic import AnthropicLLMProvider
from src.providers.llm.defaults import default_llm_model
from src.providers.llm.openai_client import (
    OpenAICompatibleLLMProvider,
    extract_chat_completion_content,
    resolve_thinking_controls,
)
from src.providers.llm.protocol import LLMProvider
from src.providers.materials.pexels import PexelsVideoProvider
from src.providers.materials.protocol import MaterialProvider
from src.providers.publishing.douyin import DouyinPublishingProvider
from src.providers.search.protocol import SearchProvider
from src.providers.search.tavily import TavilySearchProvider
from src.providers.tts.edge_tts import EdgeTTSProvider
from src.providers.tts.protocol import TTSProvider
from src.providers.tts.volcengine_tts import VolcengineTTSProvider
from src.providers.video.comfyui_video import ComfyUIVideoProvider
from src.providers.video.protocol import VideoProvider
from src.providers.video.volcengine_video import VolcengineVideoProvider
from src.repositories.provider_config_repository import ProviderConfigRepository
from src.repositories.publishing_repository import CredentialRepository, SocialAccountRepository
from src.schemas.provider import (
    ProviderConfigCreate,
    ProviderConfigUpdate,
    ProviderTestRequest,
    ProviderTestResponse,
)


class ProviderManager:
    """Core Provider Orchestration & Factory Service with Dynamic SQLite-backed Configuration

    and Fernet encryption for secret credentials.
    """

    def __init__(self, session: AsyncSession, snapshot: dict | None = None):
        self.session = session
        self.snapshot = copy.deepcopy(snapshot) if snapshot is not None else None
        self.repo = ProviderConfigRepository(session)
        self.acc_repo = SocialAccountRepository(session)
        self.cred_repo = CredentialRepository(session)

    @staticmethod
    def _snapshot_config(value):
        """Persist operational options only; credentials are resolved at use time."""
        if isinstance(value, dict):
            return {str(k): ProviderManager._snapshot_config(v) for k, v in value.items()
                    if not any(part in str(k).lower() for part in
                               ('secret', 'password', 'access_token', 'refresh_token', 'cookie', 'authorization', 'credential', 'api_key', 'apikey', 'private_key', 'app_id', 'appid'))
                    and str(k).lower() != 'token'}
        if isinstance(value, list):
            return [ProviderManager._snapshot_config(v) for v in value]
        if isinstance(value, str) and value.startswith(('http://', 'https://')):
            url = urlsplit(value)
            host = url.netloc.rsplit('@', 1)[-1]
            query = [(key, val) for key, val in parse_qsl(url.query, keep_blank_values=True)
                     if not any(part in key.lower() for part in ('key', 'secret', 'token', 'password', 'auth', 'signature'))]
            return urlunsplit((url.scheme, host, url.path, urlencode(query), ''))
        return copy.deepcopy(value)

    async def capture_snapshot(
        self,
        search_provider_id: str | None = None,
        material_provider_id: str | None = None,
    ) -> dict:
        """Freeze selected provider IDs/options, but never freeze or expose credentials."""
        if self.snapshot is None:
            result = {}
            for category in ('llm', 'search', 'image', 'video', 'tts', 'material'):
                selected_id = (
                    search_provider_id if category == 'search' else
                    material_provider_id if category == 'material' else None
                )
                model = await self._resolve_model(category, selected_id)
                if model is None:
                    result[category] = None
                else:
                    entry = {
                        'id': model.id, 'provider_type': model.provider_type,
                        'provider_name': model.provider_name, 'display_name': model.display_name,
                        'config': self._snapshot_config(model.config or {}),
                    }
                    if model.provider_type == 'material' and model.provider_name == 'pexels':
                        entry['version'] = PexelsVideoProvider.cache_version
                    result[category] = entry
            self.snapshot = result
        if search_provider_id and (self.snapshot.get('search') or {}).get('id') != search_provider_id:
            model = await self.repo.get_by_id(search_provider_id)
            if not model or model.provider_type != 'search' or not model.enabled:
                raise ValidationException('指定的搜索 Provider 不可用。')
            self.snapshot['search'] = {'id': model.id, 'provider_type': 'search', 'provider_name': model.provider_name,
                                      'display_name': model.display_name, 'config': self._snapshot_config(model.config or {})}
        if material_provider_id and (self.snapshot.get('material') or {}).get('id') != material_provider_id:
            model = await self.repo.get_by_id(material_provider_id)
            if not model or model.provider_type != 'material' or not model.enabled:
                raise ValidationException('指定的在线素材 Provider 不可用。')
            self.snapshot['material'] = {
                'id': model.id,
                'provider_type': 'material',
                'provider_name': model.provider_name,
                'display_name': model.display_name,
                'config': self._snapshot_config(model.config or {}),
                'version': PexelsVideoProvider.cache_version,
            }
        from src.services.workflow_runtime import sha256_file
        from src.services.workflow_service import workflow_service
        for category in ('image', 'video'):
            entry = self.snapshot.get(category)
            if entry and entry['provider_name'] == 'comfyui':
                default = DEFAULT_COMFYUI_IMAGE_WORKFLOW if category == 'image' else 'video/video_wan2.1_fusionx.json'
                path = workflow_service.resolve_workflow_file(entry['config'].get('default_workflow') or default)
                entry['workflow_sha256'] = await sha256_file(path) if path else None
        return copy.deepcopy(self.snapshot)

    def snapshot_fingerprint_payload(self) -> dict:
        return self._snapshot_config(self.snapshot or {})

    async def resolve_config(self, provider_type: str, provider_id: str | None = None) -> ProviderConfigModel | None:
        return await self._resolve_model(provider_type, provider_id)

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------
    async def list_providers(
        self, provider_type: str | None = None
    ) -> list[ProviderConfigModel]:
        return list(await self.repo.list_by_type(provider_type))

    @staticmethod
    def _safe_config_value(value, key: str | None = None):
        """Redact accidental secrets before a configuration summary is serialized."""
        sensitive_key = key and any(
            token in key.lower()
            for token in ("key", "secret", "token", "cookie", "password", "authorization")
        )
        if sensitive_key:
            return secret_cipher.mask_secret(str(value)) if value is not None else ""
        if isinstance(value, dict):
            return {str(k): ProviderManager._safe_config_value(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [ProviderManager._safe_config_value(item) for item in value]
        return value

    @staticmethod
    def _is_volcengine_tts(provider_type: str | None, provider_name: str | None) -> bool:
        return str(provider_type or "") == "tts" and str(provider_name or "") == "volcengine"

    @classmethod
    def _normalize_provider_credentials(
        cls,
        provider_type: str | None,
        provider_name: str | None,
        credentials: dict | None,
    ) -> dict:
        """Keep Doubao TTS credentials limited to the current API Key contract."""
        values = dict(credentials or {})
        if not cls._is_volcengine_tts(provider_type, provider_name):
            return values
        api_key = str(values.get("api_key") or "").strip()
        return {"api_key": api_key} if api_key and not secret_cipher.is_masked(api_key) else {}

    @staticmethod
    def _missing_provider_fields(model: ProviderConfigModel) -> list[str]:
        """Check stored configuration shape without claiming that a service is reachable."""
        cfg = model.config or {}
        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        missing: list[str] = []

        if model.provider_type == "llm":
            if model.provider_name != "ollama" and not str(creds.get("api_key") or "").strip():
                missing.append("API Key")
            if not str(cfg.get("base_url") or "").strip():
                missing.append("Base URL")
            if not str(cfg.get("model") or "").strip():
                missing.append("模型")
        elif model.provider_type == "search":
            if model.provider_name == "tavily" and not str(creds.get("api_key") or "").strip():
                missing.append("Tavily API Key")
        elif model.provider_type == "material":
            if model.provider_name == "pexels" and not str(creds.get("api_key") or "").strip():
                missing.append("Pexels API Key")
        elif model.provider_type in {"image", "video"}:
            if not str(cfg.get("base_url") or "").strip():
                missing.append("Base URL")
            if model.provider_name == "comfyui" and not str(cfg.get("default_workflow") or "").strip():
                missing.append("默认工作流")
            if model.provider_name == "volcengine":
                if not str(creds.get("api_key") or "").strip():
                    missing.append("API Key")
                if not str(cfg.get("model") or "").strip():
                    missing.append("模型")
        elif model.provider_type == "tts" and model.provider_name == "volcengine":
            if not str(creds.get("api_key") or "").strip():
                missing.append("X-Api-Key")
            if not str(cfg.get("base_url") or "").strip():
                missing.append("Base URL")
            if not str(cfg.get("resource_id") or "").strip():
                missing.append("Resource ID")

        return missing

    @classmethod
    def _provider_summary(cls, model: ProviderConfigModel) -> dict:
        missing_fields = cls._missing_provider_fields(model)
        if not model.enabled:
            connection_status = "disabled"
        elif missing_fields:
            connection_status = "not_configured"
        elif model.provider_type == "tts" and model.provider_name == "edge_tts":
            connection_status = "ready"
        elif model.last_test_connected is True:
            connection_status = "ready"
        elif model.last_test_connected is False:
            connection_status = "failed"
        else:
            # A persisted URL/key is not evidence that the external service is reachable.
            connection_status = "not_tested"

        last_test = None
        if model.last_test_connected is not None and model.last_tested_at is not None:
            last_test = {
                "connected": model.last_test_connected,
                "tested_at": model.last_tested_at,
                "message": model.last_test_message or "",
                "latency_ms": model.last_test_latency_ms,
            }

        return {
            "id": model.id,
            "provider_type": model.provider_type,
            "provider_name": model.provider_name,
            "display_name": model.display_name,
            "enabled": model.enabled,
            "is_default": model.is_default,
            "config": cls._safe_config_value(model.config or {}),
            "masked_credentials": model.masked_credentials,
            "has_credentials": model.has_credentials,
            "configured": model.enabled and not missing_fields,
            "connection_status": connection_status,
            "missing_fields": missing_fields,
            "last_test": last_test,
        }

    @staticmethod
    def _clear_last_test(model: ProviderConfigModel) -> None:
        """Invalidate connectivity evidence when provider settings change."""
        model.last_test_connected = None
        model.last_tested_at = None
        model.last_test_message = None
        model.last_test_latency_ms = None

    async def get_system_config_summary(self) -> dict:
        """Return one safe, non-invasive view for the system configuration center."""
        providers = await self.list_providers()
        provider_summaries = [self._provider_summary(provider) for provider in providers]

        accounts = list(await self.acc_repo.list_by_platform("douyin"))
        account_summaries: list[dict] = []
        for account in accounts:
            credential = await self.cred_repo.get_by_id(account.credential_id) if account.credential_id else None
            if not credential:
                credential_status = "not_configured"
            elif not credential.is_valid or account.status in {"error", "expired"}:
                credential_status = "failed"
            elif account.status == "disabled":
                credential_status = "disabled"
            elif account.status == "active" and credential.is_valid:
                credential_status = "ready"
            else:
                credential_status = "not_tested"
            account_summaries.append(
                {
                    "id": account.id,
                    "account_name": account.account_name,
                    "username": account.username,
                    "platform": account.platform,
                    "status": account.status,
                    "credential_present": credential is not None,
                    "credential_status": credential_status,
                }
            )

        category_labels = {
            "llm": "大语言模型",
            "search": "联网检索",
            "image": "分镜生图",
            "video": "动态视频",
            "material": "在线素材",
            "tts": "旁白配音",
            "publishing": "抖音发布",
        }
        required_categories = {"llm", "image", "tts"}
        categories: list[dict] = []
        for provider_type, label in category_labels.items():
            typed = [item for item in provider_summaries if item["provider_type"] == provider_type]
            default = next((item for item in typed if item["is_default"] and item["enabled"]), None)
            default = default or next((item for item in typed if item["enabled"]), None)

            if provider_type == "publishing":
                if not typed or not any(item["enabled"] for item in typed):
                    status = "disabled" if typed else "not_configured"
                    missing_fields = ["启用发布 Provider"]
                elif not account_summaries:
                    status = "not_configured"
                    missing_fields = ["绑定抖音账号"]
                elif any(item["credential_status"] == "failed" for item in account_summaries):
                    status = "failed"
                    missing_fields = []
                elif any(item["credential_status"] == "ready" for item in account_summaries):
                    status = "ready"
                    missing_fields = []
                else:
                    status = "not_tested"
                    missing_fields = []
            elif not default:
                status = "not_configured"
                missing_fields = ["启用默认 Provider"]
            else:
                status = default["connection_status"]
                missing_fields = default["missing_fields"]

            category_configured = bool(default and default["configured"])
            if provider_type == "publishing":
                category_configured = category_configured and bool(account_summaries)

            categories.append(
                {
                    "type": provider_type,
                    "label": label,
                    "required": provider_type in required_categories,
                    "status": status,
                    "configured": category_configured,
                    "enabled": bool(default and default["enabled"]),
                    "default_provider_id": default["id"] if default else None,
                    "default_provider_name": default["provider_name"] if default else None,
                    "missing_fields": missing_fields,
                    "provider_ids": [item["id"] for item in typed],
                    "account_count": len(account_summaries) if provider_type == "publishing" else None,
                }
            )

        missing_items = [
            {
                "category": category["type"],
                "label": category["label"],
                "required": category["required"],
                "fields": category["missing_fields"],
            }
            for category in categories
            if category["status"] in {"not_configured", "failed", "disabled"}
        ]
        required_missing = [item for item in missing_items if item["required"]]
        failed_count = sum(category["status"] == "failed" for category in categories)
        pending_test_count = sum(category["status"] == "not_tested" for category in categories)
        if required_missing or failed_count:
            overall_status = "attention"
            overall_label = "有配置需要处理"
        elif pending_test_count:
            overall_status = "not_tested"
            overall_label = "配置已保存，部分服务待连接测试"
        else:
            overall_status = "ready"
            overall_label = "核心配置已就绪"

        return {
            "generated_at": time.time(),
            "overall": {
                "status": overall_status,
                "label": overall_label,
                "configured_categories": sum(category["configured"] for category in categories),
                "ready_categories": sum(category["status"] == "ready" for category in categories),
                "pending_test_categories": pending_test_count,
                "failed_categories": failed_count,
                "missing_items": missing_items,
            },
            "system": {
                "app_name": settings.app_name,
                "app_version": settings.app_version,
                "debug": settings.debug,
            },
            "storage": {
                "database": "SQLite",
                "data_dir": str(settings.data_dir),
                "storage_dir": str(settings.storage_dir),
                "worker_count": settings.max_concurrent_workers,
                "task_timeout_seconds": settings.task_timeout_seconds,
            },
            "categories": categories,
            "providers": provider_summaries,
            "publishing": {
                "status": next(category["status"] for category in categories if category["type"] == "publishing"),
                "total_accounts": len(account_summaries),
                "pending_accounts": sum(item["credential_status"] == "not_tested" for item in account_summaries),
                "invalid_accounts": sum(item["credential_status"] == "failed" for item in account_summaries),
                "accounts": account_summaries,
            },
        }

    async def get_provider(self, provider_id: str) -> ProviderConfigModel:
        model = await self.repo.get_by_id(provider_id)
        if not model:
            raise NotFoundException("ProviderConfig", provider_id)
        return model

    async def create_provider(
        self, data: ProviderConfigCreate
    ) -> ProviderConfigModel:
        p_type_val = data.provider_type.value if hasattr(data.provider_type, "value") else str(data.provider_type)
        # Check uniqueness per type/name
        existing = await self.repo.get_by_name(
            p_type_val, data.provider_name
        )
        if existing:
            raise ValidationException(
                f"Provider '{data.provider_name}' of type '{p_type_val}' already exists."
            )

        # Encrypt credentials if provided. Doubao TTS only accepts the current API Key.
        normalized_credentials = self._normalize_provider_credentials(
            p_type_val,
            data.provider_name,
            data.credentials,
        )
        encrypted_creds = secret_cipher.encrypt_dict(normalized_credentials)
        prov_id = data.id or f"prov_{p_type_val}_{data.provider_name}"

        model = ProviderConfigModel(
            id=prov_id,
            provider_type=p_type_val,
            provider_name=data.provider_name,
            display_name=data.display_name,
            enabled=data.enabled,
            is_default=data.is_default,
            config=data.config or {},
            credentials_encrypted=encrypted_creds,
        )

        created = await self.repo.create(model)
        if data.is_default:
            await self.repo.set_default(created.id, p_type_val)
            await self.session.refresh(created)
        await self.session.commit()
        return created

    async def update_provider(
        self, provider_id: str, data: ProviderConfigUpdate
    ) -> ProviderConfigModel:
        model = await self.repo.get_by_id(provider_id)
        if not model:
            raise ValidationException(f"Provider not found: {provider_id}")

        configuration_changed = False

        if data.display_name is not None:
            model.display_name = data.display_name
        if data.enabled is not None:
            configuration_changed = configuration_changed or data.enabled != model.enabled
            model.enabled = data.enabled
        if data.config is not None:
            # Merge with existing config
            updated_config = {**model.config, **data.config}
            configuration_changed = configuration_changed or updated_config != model.config
            model.config = updated_config

        # Update credentials only if provided (don't overwrite if not specified or placeholder)
        if data.credentials is not None:
            # Filter out masked placeholders (e.g. "••••••••")
            existing_creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
            if self._is_volcengine_tts(model.provider_type, model.provider_name):
                api_key = str(data.credentials.get("api_key") or "").strip()
                cleaned_creds = (
                    {"api_key": api_key}
                    if api_key and not secret_cipher.is_masked(api_key)
                    else dict(existing_creds)
                )
            else:
                cleaned_creds = dict(existing_creds)
                for k, v in data.credentials.items():
                    if secret_cipher.is_masked(str(v)):
                        continue
                    elif v is not None and str(v).strip():
                        cleaned_creds[k] = str(v).strip()

            if cleaned_creds != existing_creds:
                configuration_changed = True
                model.credentials_encrypted = secret_cipher.encrypt_dict(cleaned_creds)

        if configuration_changed:
            self._clear_last_test(model)

        updated = await self.repo.update(model)
        if data.is_default:
            await self.repo.set_default(provider_id, model.provider_type)
        elif data.is_default is False:
            model.is_default = False
            await self.session.flush()
        await self.session.commit()
        return updated

    async def delete_provider(self, provider_id: str) -> bool:
        deleted = await self.repo.delete_by_id(provider_id)
        await self.session.commit()
        return deleted

    async def set_default_provider(self, provider_id: str) -> ProviderConfigModel:
        model = await self.repo.get_by_id(provider_id)
        if not model:
            raise ValidationException(f"Provider not found: {provider_id}")
        await self.repo.set_default(provider_id, model.provider_type)
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def toggle_provider(self, provider_id: str) -> ProviderConfigModel:
        model = await self.repo.get_by_id(provider_id)
        if not model:
            raise ValidationException(f"Provider not found: {provider_id}")
        updated = await self.repo.toggle_enabled(provider_id)
        if updated:
            self._clear_last_test(updated)
        await self.session.commit()
        return updated

    # -------------------------------------------------------------------------
    # Provider Factory Resolvers
    # -------------------------------------------------------------------------
    async def get_llm(self, provider_id: str | None = None) -> LLMProvider:
        """Get active LLM provider instance from SQLite"""
        model = await self._resolve_model("llm", provider_id)
        if not model:
            raise ValidationException(
                "未配置大语言模型服务，请前往【设置中心】配置 DeepSeek / OpenAI / Claude / Cloudflare / Ollama 等 LLM 服务。"
            )

        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        cfg = model.config or {}
        api_key = str(creds.get("api_key") or "").strip()
        configured_base_url = str(cfg.get("base_url") or "").strip()
        base_url = configured_base_url or (
            "https://api.anthropic.com/v1"
            if model.provider_name in {"claude", "anthropic"}
            else "https://api.openai.com/v1"
        )
        model_name = str(cfg.get("model") or "").strip() or default_llm_model(model.provider_name)

        # Special case: Ollama default key
        if not api_key and ("11434" in base_url or "ollama" in model.provider_name.lower()):
            api_key = "ollama"

        if not api_key:
            raise ValidationException(f"LLM Provider [{model.display_name}] 未配置 API Key。")

        if model.provider_name in {"claude", "anthropic"}:
            return AnthropicLLMProvider(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                timeout_seconds=float(cfg.get("timeout", 120.0)),
            )

        return OpenAICompatibleLLMProvider(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            timeout_seconds=float(cfg.get("timeout", 120.0)),
            provider_name=model.provider_name,
        )

    async def get_search(self, provider_id: str | None = None) -> SearchProvider:
        """Get active Search provider instance from SQLite"""
        model = await self._resolve_model("search", provider_id)
        if not model:
            raise ValidationException("未配置联网检索服务，请前往【设置中心】配置 Tavily 搜索服务。")

        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        cfg = model.config or {}
        api_key = creds.get("api_key", "").strip()

        if model.provider_name == "tavily":
            if not api_key:
                raise ValidationException("Tavily 搜索服务未配置 API Key。")
            return TavilySearchProvider(
                api_key=api_key,
                timeout_seconds=float(cfg.get("timeout", 15.0)),
            )

        raise ValidationException(f"不支持的搜索 Provider 实现: {model.provider_name}")

    async def get_material(self, provider_id: str | None = None) -> MaterialProvider:
        """Get the enabled online-material provider from the encrypted catalog."""
        model = await self._resolve_model("material", provider_id)
        if not model:
            raise ValidationException("未配置在线素材服务，请前往【系统设置】配置 Pexels API Key。")
        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        cfg = model.config or {}
        if model.provider_name != "pexels":
            raise ValidationException(f"不支持的在线素材 Provider 实现: {model.provider_name}")
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            raise ValidationException("Pexels 在线素材服务未配置 API Key。")
        return PexelsVideoProvider(
            api_key=api_key,
            timeout_seconds=float(cfg.get("timeout", 15.0)),
            download_timeout_seconds=float(cfg.get("download_timeout", 120.0)),
            max_download_bytes=int(cfg.get("max_download_bytes", 200 * 1024 * 1024)),
            locale=str(cfg.get("locale") or "en-US"),
            size=str(cfg.get("size") or "medium"),
            min_short_edge=int(cfg.get("min_short_edge", 720)),
        )

    async def get_default_tts_voice(self) -> str:
        model = await self._resolve_model("tts", None)
        fallback = (
            VolcengineTTSProvider.DEFAULT_VOICE
            if model and model.provider_name == "volcengine"
            else "zh-CN-YunxiNeural"
        )
        config = (
            VolcengineTTSProvider.normalize_legacy_defaults(model.config or {})
            if model and model.provider_name == "volcengine"
            else (model.config or {}) if model else {}
        )
        return str(config.get("default_voice") or fallback).strip() or fallback

    async def get_tts(self, provider_id: str | None = None) -> TTSProvider:
        """Get active TTS provider instance from SQLite"""
        model = await self._resolve_model("tts", provider_id)
        if not model or model.provider_name == "edge_tts":
            cfg = (model.config or {}) if model else {}
            return EdgeTTSProvider(default_voice=cfg.get("default_voice") or "zh-CN-YunxiNeural")

        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        cfg = (
            VolcengineTTSProvider.normalize_legacy_defaults(model.config or {})
            if model.provider_name == "volcengine"
            else model.config or {}
        )

        if model.provider_name == "volcengine":
            api_key = str(creds.get("api_key") or "").strip()
            if not api_key:
                raise ValidationException("豆包语音服务未配置 X-Api-Key。")
            return VolcengineTTSProvider(
                api_key=api_key,
                base_url=cfg.get("base_url", VolcengineTTSProvider.DEFAULT_BASE_URL),
                resource_id=cfg.get("resource_id", VolcengineTTSProvider.DEFAULT_RESOURCE_ID),
                model=cfg.get("model"),
                default_voice=cfg.get("default_voice", VolcengineTTSProvider.DEFAULT_VOICE),
                default_speed_ratio=cfg.get("speed_ratio", VolcengineTTSProvider.DEFAULT_SPEED_RATIO),
                timeout=float(cfg.get("timeout", 60.0)),
            )

        raise ValidationException(f"不支持的 TTS Provider 实现: {model.provider_name}")

    async def get_image(self, provider_id: str | None = None) -> ImageProvider:
        """Get active Image provider instance from SQLite"""
        model = await self._resolve_model("image", provider_id)
        if not model:
            raise ValidationException("未配置分镜画面生成服务，请前往【设置中心】配置 ComfyUI 或火山方舟。")

        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        cfg = model.config or {}

        if model.provider_name == "comfyui":
            return ComfyUIImageProvider(
                base_url=cfg.get("base_url", "http://127.0.0.1:8188"),
                api_key=creds.get("api_key"),
                default_workflow=cfg.get("default_workflow", DEFAULT_COMFYUI_IMAGE_WORKFLOW),
                timeout=float(cfg.get("timeout", 180.0)),
                generation_timeout=float(cfg.get("generation_timeout", 1800.0)),
            )
        elif model.provider_name == "volcengine":
            api_key = str(creds.get("api_key") or "").strip()
            if not api_key:
                raise ValidationException("火山方舟图像生成服务未配置 API Key。")
            return VolcengineImageProvider(
                api_key=api_key,
                base_url=cfg.get("base_url", VolcengineImageProvider.DEFAULT_BASE_URL),
                model=cfg.get("model", VolcengineImageProvider.DEFAULT_MODEL),
                timeout=float(cfg.get("timeout", 120.0)),
                watermark=bool(cfg.get("watermark", False)),
                response_format=cfg.get("response_format", "url"),
            )

        raise ValidationException(f"不支持的图像 Provider 实现: {model.provider_name}")

    async def get_video(self, provider_id: str | None = None) -> VideoProvider:
        """Get active Video provider instance from SQLite"""
        model = await self._resolve_model("video", provider_id)
        if not model:
            raise ValidationException("未配置动态视频生成服务，请前往【设置中心】配置 ComfyUI 或火山方舟 Seedance。")

        creds = secret_cipher.decrypt_dict(model.credentials_encrypted)
        cfg = model.config or {}

        if model.provider_name == "comfyui":
            return ComfyUIVideoProvider(
                base_url=cfg.get("base_url", "http://127.0.0.1:8188"),
                api_key=creds.get("api_key"),
                default_workflow=cfg.get("default_workflow", "video/video_wan2.1_fusionx.json"),
                timeout=float(cfg.get("timeout", 300.0)),
            )
        if model.provider_name == "volcengine":
            api_key = str(creds.get("api_key") or "").strip()
            if not api_key:
                raise ValidationException("火山方舟视频生成服务未配置 API Key。")
            return VolcengineVideoProvider(
                api_key=api_key,
                base_url=cfg.get("base_url", VolcengineVideoProvider.DEFAULT_BASE_URL),
                model=cfg.get("model", VolcengineVideoProvider.DEFAULT_MODEL),
                timeout=float(cfg.get("timeout", 60.0)),
                generation_timeout=float(cfg.get("generation_timeout", 1800.0)),
                poll_interval=float(cfg.get("poll_interval", 5.0)),
                resolution=cfg.get("resolution", "720p"),
                watermark=bool(cfg.get("watermark", False)),
                generate_audio=bool(cfg.get("generate_audio", False)),
            )

        raise ValidationException(f"不支持的视频 Provider 实现: {model.provider_name}")

    async def _resolve_model(self, provider_type: str, provider_id: str | None) -> ProviderConfigModel | None:
        if self.snapshot is not None and provider_type in self.snapshot:
            frozen = self.snapshot[provider_type]
            if frozen is None:
                return None
            if provider_id and frozen['id'] != provider_id:
                raise ValidationException('Provider 不匹配任务配置快照，请重新选择任务配置。')
            current = await self.repo.get_by_id(frozen['id'])
            if current is None:
                raise NotFoundException('ProviderConfig', frozen['id'])
            if not current.enabled or current.provider_type != provider_type:
                raise ValidationException('任务快照中的 Provider 已禁用或类型改变。')
            config = copy.deepcopy(frozen['config'])
            # Recover URL credentials from the current record without storing them in snapshots.
            for key, value in list(config.items()):
                live = (current.config or {}).get(key)
                if isinstance(value, str) and value.startswith(('http://', 'https://')) and isinstance(live, str):
                    old_url, live_url = urlsplit(value), urlsplit(live)
                    if (old_url.scheme, old_url.hostname, old_url.port, old_url.path) == (live_url.scheme, live_url.hostname, live_url.port, live_url.path):
                        auth = live_url.netloc.rsplit('@', 1)[0] + '@' if '@' in live_url.netloc else ''
                        private_query = [(k, v) for k, v in parse_qsl(live_url.query, keep_blank_values=True)
                                         if any(part in k.lower() for part in ('key', 'secret', 'token', 'password', 'auth', 'signature'))]
                        config[key] = urlunsplit((old_url.scheme, auth + old_url.netloc, old_url.path,
                                                 urlencode(parse_qsl(old_url.query, keep_blank_values=True) + private_query), ''))
            return ProviderConfigModel(id=frozen['id'], provider_type=provider_type,
                provider_name=frozen['provider_name'], display_name=frozen['display_name'], enabled=True,
                config=config, credentials_encrypted=current.credentials_encrypted)
        if provider_id:
            model = await self.repo.get_by_id(provider_id)
            if not model:
                raise NotFoundException("ProviderConfig", provider_id)
            if model.provider_type != provider_type:
                raise ValidationException(
                    f"Provider [{provider_id}] 类型为 {model.provider_type}，不能用于 {provider_type}。"
                )
            if not model.enabled:
                raise ValidationException(f"Provider [{model.display_name}] 已被禁用。")
            return model
        return await self.repo.get_default(provider_type)

    # -------------------------------------------------------------------------
    # Live Connectivity Testing
    # -------------------------------------------------------------------------
    async def test_provider(self, req: ProviderTestRequest) -> ProviderTestResponse:
        """Execute real connection handshake and return latency and status"""
        prov_type = req.provider_type
        prov_name = req.provider_name
        cfg = dict(req.config or {})
        creds = dict(req.credentials or {})
        db_model: ProviderConfigModel | None = None
        persist_result = False

        if req.provider_id:
            db_model = await self.repo.get_by_id(req.provider_id)
            if not db_model:
                raise NotFoundException("ProviderConfig", req.provider_id)
            if req.provider_type and req.provider_type != db_model.provider_type:
                raise ValidationException(
                    f"Provider [{req.provider_id}] 类型为 {db_model.provider_type}，不能用于 {req.provider_type}。"
                )
            if req.provider_name and req.provider_name != db_model.provider_name:
                raise ValidationException(
                    f"Provider [{req.provider_id}] 名称为 {db_model.provider_name}，不能按 {req.provider_name} 测试。"
                )

            prov_type = prov_type or db_model.provider_type
            prov_name = prov_name or db_model.provider_name
            request_config = dict(req.config or {})
            cfg = {**db_model.config, **request_config}
            db_creds = secret_cipher.decrypt_dict(db_model.credentials_encrypted)
            request_changes_config = any(
                (db_model.config or {}).get(key) != value
                for key, value in request_config.items()
            )
            request_changes_credentials = any(
                not secret_cipher.is_masked(str(value)) and db_creds.get(key) != value
                for key, value in creds.items()
            )
            persist_result = not request_changes_config and not request_changes_credentials
            for k, v in creds.items():
                if secret_cipher.is_masked(str(v)):
                    creds[k] = db_creds.get(k, "")
            # Fill missing keys from DB
            for k, v in db_creds.items():
                if k not in creds:
                    creds[k] = v

            # Do not hold the provider lookup's SQLite read transaction while
            # a local or remote provider is running. Long image generation
            # jobs can otherwise make the later test-status write contend with
            # workflow persistence and turn a successful preview into a 500.
            await self.session.rollback()

        if not prov_type:
            return ProviderTestResponse(
                connected=False,
                message="未指定待测试的 Provider，请提供 provider_id 或 provider_type。",
            )

        try:
            if prov_type == "llm":
                if (prov_name or "").lower() in {"claude", "anthropic"}:
                    result = await self._test_anthropic_connection(cfg, creds)
                else:
                    result = await self._test_llm_connection(cfg, creds, prov_name)
            elif prov_type == "search":
                result = await self._test_search_connection(cfg, creds, req.test_payload)
            elif prov_type == "material":
                result = await self._test_material_connection(cfg, creds, prov_name or "pexels")
            elif prov_type == "image" and req.test_payload and req.test_payload.get("operation") == "generate":
                result = await self._test_image_generation(cfg, creds, prov_name or "comfyui", req.test_payload)
            elif prov_type in ("image", "video") and prov_name == "comfyui":
                result = await self._test_comfyui_connection(cfg, creds)
            elif prov_type in ("image", "video") and prov_name == "volcengine":
                result = await self._test_volcengine_ark_connection(cfg, creds, prov_type)
            elif prov_type == "tts":
                result = await self._test_tts_connection(prov_name or "edge_tts", cfg, creds)
            elif prov_type == "publishing":
                result = await self._test_publishing_connection()
            else:
                result = ProviderTestResponse(
                    connected=False,
                    message=f"不支持的 Provider 类型: {prov_type}。",
                )
        except Exception as exc:
            logger.exception("Provider connectivity test raised an unexpected exception")
            result = ProviderTestResponse(
                connected=False,
                message=f"测试连接异常（{type(exc).__name__}），请检查 Provider 配置。",
            )

        if db_model and persist_result:
            try:
                db_model.last_test_connected = result.connected
                db_model.last_tested_at = datetime.now(UTC)
                db_model.last_test_message = redact_sensitive_text(result.message)
                db_model.last_test_latency_ms = result.latency_ms
                await self.session.commit()
            except Exception as exc:
                # A preview response must not be discarded when SQLite is
                # briefly locked by another local workflow. The test result
                # remains valid; only its optional status evidence is lost.
                try:
                    await self.session.rollback()
                except Exception as rollback_exc:
                    logger.warning(
                        "Provider test status rollback also failed: {}",
                        redact_sensitive_text(str(rollback_exc)),
                    )
                logger.warning(
                    "Provider test succeeded but persisting test evidence failed: {}",
                    redact_sensitive_text(str(exc)),
                )

        return result

    async def _test_image_generation(
        self,
        cfg: dict,
        creds: dict,
        provider_name: str,
        test_payload: dict,
    ) -> ProviderTestResponse:
        """Generate one in-memory image to verify the configured image provider."""
        prompt = str(test_payload.get("prompt") or DEFAULT_IMAGE_TEST_PROMPT).strip()
        aspect_ratio = str(test_payload.get("aspect_ratio") or "16:9")
        style_preset = str(test_payload.get("style_preset") or DEFAULT_IMAGE_STYLE_PRESET).strip()
        api_key = str(creds.get("api_key") or "").strip()

        if provider_name == "comfyui":
            default_workflow = cfg.get("default_workflow") or DEFAULT_COMFYUI_IMAGE_WORKFLOW
            provider = ComfyUIImageProvider(
                base_url=cfg.get("base_url") or "http://127.0.0.1:8188",
                api_key=api_key or None,
                default_workflow=default_workflow,
                timeout=float(cfg.get("timeout", 120.0)),
                generation_timeout=float(cfg.get("generation_timeout", 1800.0)),
            )
        elif provider_name == "volcengine":
            if not api_key:
                return ProviderTestResponse(
                    connected=False,
                    message="未配置火山方舟图像生成 API Key，请先填写密钥。",
                )
            provider = VolcengineImageProvider(
                api_key=api_key,
                base_url=cfg.get("base_url") or VolcengineImageProvider.DEFAULT_BASE_URL,
                model=cfg.get("model") or VolcengineImageProvider.DEFAULT_MODEL,
                timeout=float(cfg.get("timeout", 120.0)),
                watermark=bool(cfg.get("watermark", False)),
                response_format=cfg.get("response_format", "url"),
            )
        else:
            return ProviderTestResponse(
                connected=False,
                message=f"不支持的图像 Provider 实现: {provider_name}",
            )

        workflow_override = str(test_payload.get("workflow") or "").strip() or None
        workflow = workflow_override
        if workflow is None and provider_name != "comfyui":
            workflow = cfg.get("default_workflow") or getattr(provider, "default_workflow", None)
        start_time = time.perf_counter()
        try:
            result = await provider.generate_image(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                style_preset=style_preset,
                # None means "exercise the provider's configured default".
                # A test payload may supply an explicit one-off override; the
                # ComfyUI provider never applies its default compatibility
                # retry to that override.
                workflow=workflow,
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            if not result.image_bytes:
                return ProviderTestResponse(
                    connected=False,
                    message="图像生成服务返回空图像。",
                    latency_ms=latency_ms,
                )
            data_url = (
                f"data:{result.mime_type};base64,"
                f"{base64.b64encode(result.image_bytes).decode('ascii')}"
            )
            return ProviderTestResponse(
                connected=True,
                message="图片生成测试成功。",
                latency_ms=latency_ms,
                details={
                    "image_url": data_url,
                    "width": result.width,
                    "height": result.height,
                    "format": result.format,
                },
            )
        except Exception as exc:
            return ProviderTestResponse(
                connected=False,
                message=f"{provider_name} 图片生成测试失败: {redact_sensitive_text(str(exc))}",
                latency_ms=round((time.perf_counter() - start_time) * 1000, 1),
            )

    async def _test_publishing_connection(self) -> ProviderTestResponse:
        """Test Douyin publishing status by inspecting accounts in database."""
        accounts = await self.acc_repo.list_by_platform("douyin")
        if not accounts:
            return ProviderTestResponse(
                connected=True,
                message="抖音发布引擎就绪。当前尚未绑定抖音账号，请在卡片内点击【抖音扫码绑定】进行登录授权。",
            )

        valid_count = 0
        prov = DouyinPublishingProvider()
        for acc in accounts:
            if acc.credential_id:
                cred_m = await self.cred_repo.get_by_id(acc.credential_id)
                if cred_m and cred_m.payload:
                    is_valid = await prov.validate_account(cred_m.payload)
                    if is_valid:
                        valid_count += 1
                        acc.status = "active"
                        cred_m.is_valid = True
                    else:
                        acc.status = "error"
                        cred_m.is_valid = False
                    acc.updated_at = datetime.now(UTC)
                    cred_m.updated_at = datetime.now(UTC)
                    await self.acc_repo.update(acc)
                    await self.cred_repo.update(cred_m)
        await self.session.commit()

        if valid_count > 0:
            return ProviderTestResponse(
                connected=True,
                message=f"抖音创作者中心服务正常，已连接 {len(accounts)} 个账号 (其中 {valid_count} 个凭证处于有效状态)。",
                details={"total_accounts": len(accounts), "valid_accounts": valid_count},
            )
        else:
            return ProviderTestResponse(
                connected=False,
                message=f"已绑定 {len(accounts)} 个抖音账号，但登录状态已过期，请在下方点击【重新扫码】刷新授权。",
                details={"total_accounts": len(accounts), "valid_accounts": 0},
            )

    async def _test_llm_connection(
        self,
        cfg: dict,
        creds: dict,
        provider_name: str | None = None,
    ) -> ProviderTestResponse:
        import httpx

        api_key = creds.get("api_key", "").strip()
        base_url = (str(cfg.get("base_url") or "").strip() or "https://api.openai.com/v1").rstrip("/")
        safe_base_url = redact_sensitive_text(base_url)
        model = str(cfg.get("model") or "").strip() or default_llm_model(provider_name)
        thinking_fields, thinking_strategy, thinking_warning = resolve_thinking_controls(
            provider_name,
            base_url,
            model,
        )

        if not api_key:
            if (
                (provider_name or "").lower() == "ollama"
                or "11434" in base_url
                or "ollama" in model.lower()
            ):
                api_key = "ollama"
            else:
                return ProviderTestResponse(
                    connected=False,
                    message="未配置或未输入 API Key，请先填写大语言模型 API 密钥。",
                )

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "temperature": 0.0,
            "stream": False,
        }
        body.update(thinking_fields)

        if thinking_warning:
            # Keep the connection-test path aligned with the generation path,
            # including the explicit warning for forced reasoning models.
            logger.warning(f"{thinking_warning} strategy={thinking_strategy}")

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                res = await client.post(f"{base_url}/chat/completions", json=body, headers=headers)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

                if res.status_code == 200:
                    data = res.json()
                    reply = ""
                    if isinstance(data, dict):
                        # 如果网关在 HTTP 200 下返回了 error 对象
                        if "error" in data and data["error"]:
                            err_val = data["error"]
                            err_msg = (
                                err_val.get("message", str(err_val))
                                if isinstance(err_val, dict)
                                else str(err_val)
                            )
                            return ProviderTestResponse(
                                connected=False,
                                message=f"大模型返回错误: {redact_sensitive_text(err_msg)}",
                                latency_ms=latency_ms,
                            )
                        if "detail" in data and isinstance(data["detail"], str) and "choices" not in data:
                            return ProviderTestResponse(
                                connected=False,
                                message=f"大模型返回错误: {redact_sensitive_text(data['detail'])}",
                                latency_ms=latency_ms,
                            )

                        choices = data.get("choices")
                        if isinstance(choices, list) and len(choices) > 0 and isinstance(choices[0], dict):
                            msg = choices[0].get("message")
                            if isinstance(msg, dict):
                                reply = extract_chat_completion_content(data)

                    reply = reply or ""
                    if not reply.strip():
                        return ProviderTestResponse(
                            connected=False,
                            message="大模型返回了空内容，连接未通过。请检查模型 ID、网关协议与额度。",
                            latency_ms=latency_ms,
                            details={"model": model, "reply": ""},
                        )
                    return ProviderTestResponse(
                        connected=True,
                        message=f"成功连接至大模型服务 (耗时 {latency_ms}ms, 模型: {model})",
                        latency_ms=latency_ms,
                        details={"model": model, "reply": reply[:100]},
                    )
                elif res.status_code in (401, 403):
                    return ProviderTestResponse(
                        connected=False,
                        message=f"大模型认证失败 (HTTP {res.status_code})：API Key 无效或未授权该模型 ({model})。",
                        latency_ms=latency_ms,
                    )
                elif res.status_code == 404:
                    return ProviderTestResponse(
                        connected=False,
                        message=f"接口路径不存在 (HTTP 404)：请检查 Base URL ({safe_base_url}) 是否正确或需添加 /v1。",
                        latency_ms=latency_ms,
                    )
                else:
                    return ProviderTestResponse(
                        connected=False,
                        message=f"大模型服务返回异常 (HTTP {res.status_code}): {redact_sensitive_text(res.text[:200])}",
                        latency_ms=latency_ms,
                    )
        except httpx.RemoteProtocolError:
            return ProviderTestResponse(
                connected=False,
                message="大模型服务器在返回响应前关闭了连接（直连模式），请检查 Cloudflare 网络连通性或 API Token。",
            )
        except httpx.ConnectError:
            return ProviderTestResponse(
                connected=False,
                message=f"无法连接至 Base URL ({safe_base_url})（直连模式），请确认网络连接或本地服务已启动。",
            )
        except httpx.TimeoutException:
            return ProviderTestResponse(
                connected=False,
                message=f"连接大语言模型服务超时 (10.0s)，请检查 Base URL ({safe_base_url}) 连通性。",
            )
        except httpx.RequestError as e:
            return ProviderTestResponse(
                connected=False,
                message=f"大模型网络请求失败（{type(e).__name__}，直连模式），请检查网络或 Base URL。",
            )
        except Exception as e:
            return ProviderTestResponse(
                connected=False,
                message=f"测试连接异常（{type(e).__name__}），请检查 Provider 配置。",
            )

    async def _test_anthropic_connection(
        self, cfg: dict, creds: dict
    ) -> ProviderTestResponse:
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return ProviderTestResponse(
                connected=False,
                message="未配置或未输入 Anthropic API Key，请先填写密钥。",
            )

        model = str(cfg.get("model") or default_llm_model("claude")).strip()
        base_url = str(cfg.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
        start_time = time.perf_counter()
        try:
            provider = AnthropicLLMProvider(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=10.0,
            )
            reply = await provider.generate_text("Hi", max_tokens=8)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            if not reply.strip():
                return ProviderTestResponse(
                    connected=False,
                    message="Anthropic 返回了空内容，连接未通过。请检查模型 ID 与额度。",
                    latency_ms=latency_ms,
                    details={"model": model, "reply": ""},
                )
            return ProviderTestResponse(
                connected=True,
                message=f"成功连接至 Anthropic 服务 (耗时 {latency_ms}ms, 模型: {model})",
                latency_ms=latency_ms,
                details={"model": model, "reply": reply[:100]},
            )
        except ProviderException as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return ProviderTestResponse(
                connected=False,
                message=redact_sensitive_text(str(exc)),
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return ProviderTestResponse(
                connected=False,
                message=f"Anthropic 连接测试异常（{type(exc).__name__}），请检查 Provider 配置。",
                latency_ms=latency_ms,
            )

    async def _test_search_connection(self, cfg: dict, creds: dict, test_payload: dict | None) -> ProviderTestResponse:
        import httpx

        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return ProviderTestResponse(
                connected=False,
                message="未配置或未输入 Tavily API Key，请先填写密钥。",
            )

        query = (test_payload or {}).get("query") or "Trendlume"
        url = "https://api.tavily.com/search"
        req_body = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": 1,
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=req_body)
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

                if res.status_code == 200:
                    data = res.json()
                    results = data.get("results", [])
                    return ProviderTestResponse(
                        connected=True,
                        message=f"成功连接至 Tavily 实时搜索服务 (耗时 {latency_ms}ms)，返回 {len(results)} 条检索结果",
                        latency_ms=latency_ms,
                        details={"results_count": len(results)},
                    )
                elif res.status_code in (401, 403):
                    return ProviderTestResponse(
                        connected=False,
                        message=f"Tavily 认证失败 (HTTP {res.status_code})：API Key 无效或配额耗尽。",
                        latency_ms=latency_ms,
                    )
                else:
                    return ProviderTestResponse(
                        connected=False,
                        message=f"Tavily 返回异常 (HTTP {res.status_code}): {res.text[:200]}",
                        latency_ms=latency_ms,
                    )
        except Exception as e:
            return ProviderTestResponse(connected=False, message=f"Tavily 搜索测试连接异常: {e}")

    async def _test_material_connection(
        self,
        cfg: dict,
        creds: dict,
        provider_name: str,
    ) -> ProviderTestResponse:
        if provider_name != "pexels":
            return ProviderTestResponse(connected=False, message=f"不支持的在线素材 Provider: {provider_name}")
        api_key = str(creds.get("api_key") or "").strip()
        if not api_key:
            return ProviderTestResponse(connected=False, message="未配置 Pexels API Key，请先填写密钥。")
        provider = PexelsVideoProvider(
            api_key=api_key,
            timeout_seconds=float(cfg.get("timeout", 15.0)),
            locale=str(cfg.get("locale") or "en-US"),
            size=str(cfg.get("size") or "medium"),
        )
        query = str(cfg.get("test_query") or "nature").strip() or "nature"
        start_time = time.perf_counter()
        try:
            results = await provider.search(query, "9:16", 0.0, 1)
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return ProviderTestResponse(
                connected=True,
                message=f"成功连接 Pexels 在线素材服务（耗时 {latency_ms}ms），返回 {len(results)} 条候选。",
                latency_ms=latency_ms,
                details={"results_count": len(results)},
            )
        except Exception as exc:
            return ProviderTestResponse(
                connected=False,
                message=f"Pexels 连接测试失败（{type(exc).__name__}），请检查 API Key 和网络。",
                latency_ms=round((time.perf_counter() - start_time) * 1000, 1),
            )

    async def _test_comfyui_connection(self, cfg: dict, creds: dict) -> ProviderTestResponse:
        import httpx

        base_url = (cfg.get("base_url") or "http://127.0.0.1:8188").rstrip("/")
        api_key = creds.get("api_key", "").strip()

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=4.0, headers=headers) as client:
                res = await client.get(f"{base_url}/system_stats")
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                if res.status_code == 200:
                    data = res.json()
                    devices = data.get("devices", [])
                    vram_info = ""
                    if devices and isinstance(devices, list):
                        vram_free = devices[0].get("vram_free", 0) / (1024 * 1024 * 1024)
                        vram_info = f" (显存剩余: {vram_free:.1f} GB)"
                    return ProviderTestResponse(
                        connected=True,
                        message=f"成功连接至本地 ComfyUI 服务 (耗时 {latency_ms}ms){vram_info}",
                        latency_ms=latency_ms,
                        details=data,
                    )
                else:
                    return ProviderTestResponse(
                        connected=False,
                        message=f"ComfyUI 返回 HTTP {res.status_code}",
                        latency_ms=latency_ms,
                    )
        except Exception as e:
            return ProviderTestResponse(
                connected=False,
                message=f"无法连接至 ComfyUI 服务 ({base_url})，请确认本地 ComfyUI 已启动: {e}",
            )

    async def _test_volcengine_ark_connection(
        self,
        cfg: dict,
        creds: dict,
        provider_type: str,
    ) -> ProviderTestResponse:
        import httpx

        base_url = (cfg.get("base_url") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        api_key = str(creds.get("api_key") or "").strip()
        model = str(cfg.get("model") or "").strip()
        if not api_key:
            return ProviderTestResponse(connected=False, message="未配置火山方舟 API Key，请先填写密钥。")
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
            if response.status_code < 200 or response.status_code >= 300:
                return ProviderTestResponse(
                    connected=False,
                    message=f"火山方舟 {provider_type} 服务返回 HTTP {response.status_code}: "
                    f"{redact_sensitive_text(response.text[:300])}",
                    latency_ms=latency_ms,
                )
            return ProviderTestResponse(
                connected=True,
                message=f"已连接火山方舟 {provider_type} 服务。",
                latency_ms=latency_ms,
                details={"model": model or None},
            )
        except Exception as exc:
            return ProviderTestResponse(
                connected=False,
                message=f"火山方舟 {provider_type} 连接测试失败: {redact_sensitive_text(str(exc))}",
                latency_ms=round((time.perf_counter() - start_time) * 1000, 1),
            )

    async def _test_tts_connection(self, provider_name: str, cfg: dict, creds: dict) -> ProviderTestResponse:
        if provider_name == "edge_tts":
            provider = EdgeTTSProvider()
            voices = await provider.list_voices()
            return ProviderTestResponse(
                connected=True,
                message=f"微软 Edge-TTS 神经网络语音就绪，已加载 {len(voices)} 款音色。",
                details={"voices_count": len(voices)},
            )
        if provider_name == "volcengine":
            cfg = VolcengineTTSProvider.normalize_legacy_defaults(cfg)
            api_key = str(creds.get("api_key") or "").strip()
            if not api_key:
                return ProviderTestResponse(
                    connected=False,
                    message="未配置豆包语音 X-Api-Key。",
                )
            provider = VolcengineTTSProvider(
                api_key=api_key,
                base_url=cfg.get("base_url", VolcengineTTSProvider.DEFAULT_BASE_URL),
                resource_id=cfg.get("resource_id", VolcengineTTSProvider.DEFAULT_RESOURCE_ID),
                model=cfg.get("model"),
                default_voice=cfg.get("default_voice", VolcengineTTSProvider.DEFAULT_VOICE),
                default_speed_ratio=cfg.get("speed_ratio", VolcengineTTSProvider.DEFAULT_SPEED_RATIO),
                timeout=float(cfg.get("timeout", 60.0)),
            )
            start_time = time.perf_counter()
            try:
                result = await provider.synthesize("Trendlume 语音测试。")
                latency_ms = round((time.perf_counter() - start_time) * 1000, 1)
                return ProviderTestResponse(
                    connected=bool(result.audio_bytes),
                    message="豆包语音合成测试成功。" if result.audio_bytes else "豆包语音返回空音频。",
                    latency_ms=latency_ms,
                    details={"duration_seconds": result.duration_seconds},
                )
            except Exception as exc:
                return ProviderTestResponse(
                    connected=False,
                    message=f"豆包语音连接测试失败: {redact_sensitive_text(str(exc))}",
                    latency_ms=round((time.perf_counter() - start_time) * 1000, 1),
                )
        return ProviderTestResponse(connected=False, message=f"不支持的 TTS Provider 实现: {provider_name}")
