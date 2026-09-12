from __future__ import annotations

import httpx
import pytest
from src.core.exceptions import ValidationException
from src.core.security import secret_cipher
from src.models.provider_config import ProviderConfigModel
from src.providers.image.volcengine_image import VolcengineImageProvider
from src.providers.image.protocol import ImageResult
from src.providers.tts.volcengine_tts import VolcengineTTSProvider
from src.providers.video.volcengine_video import VolcengineVideoProvider
from src.schemas.provider import ProviderConfigUpdate, ProviderTestRequest
from src.services.provider_manager import ProviderManager


async def _add_provider(test_session, *, provider_type: str, provider_name: str, provider_id: str, config: dict, credentials: dict):
    model = ProviderConfigModel(
        id=provider_id,
        provider_type=provider_type,
        provider_name=provider_name,
        display_name=provider_name,
        enabled=True,
        is_default=False,
        config=config,
        credentials_encrypted=secret_cipher.encrypt_dict(credentials),
    )
    test_session.add(model)
    await test_session.commit()
    return model


@pytest.mark.asyncio
async def test_provider_manager_builds_volcengine_media_providers(test_session):
    image = await _add_provider(
        test_session,
        provider_type="image",
        provider_name="volcengine",
        provider_id="volc-image",
        config={"base_url": "https://ark.example/api/v3", "model": "seedream-test"},
        credentials={"api_key": "image-key"},
    )
    video = await _add_provider(
        test_session,
        provider_type="video",
        provider_name="volcengine",
        provider_id="volc-video",
        config={"base_url": "https://ark.example/api/v3", "model": "seedance-test"},
        credentials={"api_key": "video-key"},
    )
    tts = await _add_provider(
        test_session,
        provider_type="tts",
        provider_name="volcengine",
        provider_id="volc-tts",
        config={
            "base_url": "https://speech.example/v3",
            "resource_id": "resource-test",
            "default_voice": "voice-test",
            "speed_ratio": 1.4,
        },
        credentials={"api_key": "tts-key-old"},
    )

    manager = ProviderManager(test_session)
    image_provider = await manager.get_image(image.id)
    video_provider = await manager.get_video(video.id)
    tts_provider = await manager.get_tts(tts.id)

    assert isinstance(image_provider, VolcengineImageProvider)
    assert image_provider.api_key == "image-key"
    assert image_provider.model == "seedream-test"
    assert isinstance(video_provider, VolcengineVideoProvider)
    assert video_provider.api_key == "video-key"
    assert video_provider.model == "seedance-test"
    assert isinstance(tts_provider, VolcengineTTSProvider)
    assert tts_provider.api_key == "tts-key-old"
    assert tts_provider.default_voice == "voice-test"
    assert tts_provider.default_speed_ratio == 1.4


@pytest.mark.asyncio
async def test_provider_manager_normalizes_legacy_volcengine_tts_defaults(test_session):
    tts = await _add_provider(
        test_session,
        provider_type="tts",
        provider_name="volcengine",
        provider_id="legacy-volc-tts",
        config={
            "resource_id": "volc.service_type.10029",
            "default_voice": "zh_female_cancan_mars_bigtts",
        },
        credentials={"api_key": "tts-key"},
    )

    provider = await ProviderManager(test_session).get_tts(tts.id)

    assert isinstance(provider, VolcengineTTSProvider)
    assert provider.resource_id == "seed-tts-2.0"
    assert provider.default_voice == "zh_female_vv_uranus_bigtts"


@pytest.mark.asyncio
async def test_provider_manager_tests_ark_connection_with_bearer_key(test_session, monkeypatch):
    provider = await _add_provider(
        test_session,
        provider_type="image",
        provider_name="volcengine",
        provider_id="test-volc-image",
        config={"base_url": "https://ark.example/api/v3", "model": "seedream-test"},
        credentials={"api_key": "ark-secret"},
    )
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, headers=None):
            calls.append((url, headers or {}))
            return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    result = await ProviderManager(test_session).test_provider(
        ProviderTestRequest(provider_id=provider.id, provider_type="image", provider_name="volcengine")
    )

    assert result.connected is True
    assert calls == [
        (
            "https://ark.example/api/v3/models",
            {"Authorization": "Bearer ark-secret"},
        )
    ]


@pytest.mark.asyncio
async def test_provider_manager_generates_volcengine_image_for_test(test_session, monkeypatch):
    provider = await _add_provider(
        test_session,
        provider_type="image",
        provider_name="volcengine",
        provider_id="generate-volc-image",
        config={"base_url": "https://ark.example/api/v3", "model": "seedream-test"},
        credentials={"api_key": "ark-secret"},
    )

    async def fake_generate(self, prompt, aspect_ratio="9:16", style_preset="cinematic", workflow=None, **kwargs):
        assert prompt == "测试图片"
        assert aspect_ratio == "1:1"
        assert style_preset == "chinese_ink"
        return ImageResult(image_bytes=b"volc-image-fixture", width=1024, height=1024)

    monkeypatch.setattr(VolcengineImageProvider, "generate_image", fake_generate)
    result = await ProviderManager(test_session).test_provider(
        ProviderTestRequest(
            provider_id=provider.id,
            provider_type="image",
            provider_name="volcengine",
            test_payload={
                "operation": "generate",
                "prompt": "测试图片",
                "aspect_ratio": "1:1",
                "style_preset": "chinese_ink",
            },
        )
    )

    assert result.connected is True
    assert result.details["image_url"] == "data:image/png;base64,dm9sYy1pbWFnZS1maXh0dXJl"
    assert result.details["width"] == 1024
    assert result.details["height"] == 1024


@pytest.mark.asyncio
async def test_provider_manager_rejects_openai_media_and_rotates_tts_credentials(test_session):
    old_tts = await _add_provider(
        test_session,
        provider_type="tts",
        provider_name="openai_tts",
        provider_id="old-openai-tts",
        config={"base_url": "https://api.openai.com/v1", "model": "tts-1"},
        credentials={"api_key": "old-key"},
    )
    old_image = await _add_provider(
        test_session,
        provider_type="image",
        provider_name="openai",
        provider_id="old-openai-image",
        config={"base_url": "https://api.openai.com/v1", "model": "dall-e-3"},
        credentials={"api_key": "old-key"},
    )
    with pytest.raises(ValidationException, match="不支持的 TTS Provider"):
        await ProviderManager(test_session).get_tts(old_tts.id)
    with pytest.raises(ValidationException, match="不支持的图像 Provider"):
        await ProviderManager(test_session).get_image(old_image.id)

    volc_tts = await _add_provider(
        test_session,
        provider_type="tts",
        provider_name="volcengine",
        provider_id="rotate-volc-tts",
        config={
            "base_url": "https://speech.example/v3",
            "resource_id": "resource-test",
            "default_voice": "voice-test",
        },
        credentials={"app_id": "legacy-app", "access_token": "legacy-token"},
    )
    manager = ProviderManager(test_session)
    await manager.update_provider(
        volc_tts.id,
        ProviderConfigUpdate(credentials={"api_key": "tts-key-new"}),
    )
    refreshed = await manager.get_tts(volc_tts.id)
    assert isinstance(refreshed, VolcengineTTSProvider)
    assert refreshed.api_key == "tts-key-new"
    assert secret_cipher.decrypt_dict(volc_tts.credentials_encrypted) == {"api_key": "tts-key-new"}


def test_volcengine_required_fields_are_reported():
    model = ProviderConfigModel(
        id="missing-volc-tts",
        provider_type="tts",
        provider_name="volcengine",
        display_name="Volcengine",
        enabled=True,
        is_default=False,
        config={},
        credentials_encrypted=None,
    )
    assert set(ProviderManager._missing_provider_fields(model)) == {
        "X-Api-Key",
        "Base URL",
        "Resource ID",
    }
