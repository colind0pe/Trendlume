import json

import pytest
from httpx import AsyncClient

from src.providers.image.comfyui_image import ComfyUIImageProvider
from src.providers.image.protocol import DEFAULT_IMAGE_TEST_PROMPT, ImageResult
from src.providers.publishing.douyin import DouyinPublishingProvider
from src.providers.tts.edge_tts import EdgeTTSProvider
from src.providers.tts.protocol import TTSResult
from src.schemas.provider import ProviderTestResponse
from src.services.provider_manager import ProviderManager


async def _create_llm_provider(
    client: AsyncClient,
    *,
    provider_name: str,
    model: str,
    api_key: str,
    display_name: str | None = None,
) -> dict:
    response = await client.post(
        "/api/v1/providers",
        json={
            "provider_type": "llm",
            "provider_name": provider_name,
            "display_name": display_name or provider_name,
            "config": {"base_url": "https://example.invalid/v1", "model": model},
            "credentials": {"api_key": api_key},
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def _provider_summary(client: AsyncClient, provider_id: str) -> dict:
    response = await client.get("/api/v1/providers/summary")
    assert response.status_code == 200
    return next(item for item in response.json()["data"]["providers"] if item["id"] == provider_id)


@pytest.mark.asyncio
async def test_voice_routes_honor_selected_provider(client: AsyncClient, monkeypatch):
    voices = await client.get("/api/v1/providers/voices?provider_id=prov_tts_edge")
    assert voices.status_code == 200
    assert voices.json()["data"]

    async def fake_synthesize(self, text, voice_id=None, speed=1.0):
        assert text == "试听文本"
        assert voice_id == "zh-CN-YunxiNeural"
        assert speed == 1.4
        return TTSResult(
            audio_bytes=b"audio-fixture",
            duration_seconds=1.0,
            format="mp3",
            mime_type="audio/mpeg",
        )

    monkeypatch.setattr(EdgeTTSProvider, "synthesize", fake_synthesize)
    response = await client.post(
        "/api/v1/providers/voices/test",
        json={
            "provider_id": "prov_tts_edge",
            "voice_id": "zh-CN-YunxiNeural",
            "text": "试听文本",
            "speed_ratio": 1.4,
        },
    )
    assert response.status_code == 200
    assert response.content == b"audio-fixture"
    assert response.headers["x-duration-seconds"] == "1.0"


@pytest.mark.asyncio
async def test_image_generation_test_returns_preview_and_persists_status(
    client: AsyncClient, monkeypatch
):
    async def fake_generate(self, prompt, aspect_ratio="9:16", style_preset="cinematic", workflow=None, **kwargs):
        assert prompt == DEFAULT_IMAGE_TEST_PROMPT
        assert aspect_ratio == "16:9"
        assert style_preset == "cinematic_real"
        assert workflow is None
        return ImageResult(image_bytes=b"image-fixture", width=1280, height=720)

    monkeypatch.setattr(ComfyUIImageProvider, "generate_image", fake_generate)
    response = await client.post(
        "/api/v1/providers/image/test-generate",
        json={
            "provider_id": "prov_image_comfyui",
            "provider_name": "comfyui",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["connected"] is True
    assert data["message"] == "图片生成测试成功。"
    assert data["image_url"] == "data:image/png;base64,aW1hZ2UtZml4dHVyZQ=="
    assert data["width"] == 1280
    assert data["height"] == 720

    provider = await _provider_summary(client, "prov_image_comfyui")
    assert provider["connection_status"] == "ready"
    assert provider["last_test"]["connected"] is True


@pytest.mark.asyncio
async def test_image_generation_preview_survives_status_persistence_error(
    client: AsyncClient, test_session, monkeypatch
):
    async def fake_generate(self, *args, **kwargs):
        return ImageResult(image_bytes=b"image-fixture", width=1280, height=720)

    async def fail_commit():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(ComfyUIImageProvider, "generate_image", fake_generate)
    monkeypatch.setattr(test_session, "commit", fail_commit)

    response = await client.post(
        "/api/v1/providers/image/test-generate",
        json={
            "provider_id": "prov_image_comfyui",
            "provider_name": "comfyui",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["image_url"] == "data:image/png;base64,aW1hZ2UtZml4dHVyZQ=="


@pytest.mark.asyncio
async def test_saved_image_preview_releases_read_transaction_before_generation(
    client: AsyncClient, monkeypatch
):
    async def fake_test_image(self, cfg, creds, provider_name, test_payload):
        assert not self.session.in_transaction()
        return ProviderTestResponse(
            connected=True,
            message="图片生成测试成功。",
            details={"image_url": "data:image/png;base64,aW1hZ2UtZml4dHVyZQ=="},
        )

    monkeypatch.setattr(ProviderManager, "_test_image_generation", fake_test_image)

    response = await client.post(
        "/api/v1/providers/image/test-generate",
        json={
            "provider_id": "prov_image_comfyui",
            "provider_name": "comfyui",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["image_url"] == "data:image/png;base64,aW1hZ2UtZml4dHVyZQ=="


@pytest.mark.asyncio
async def test_provider_rest_endpoints(client: AsyncClient):
    # 1. List Providers
    res_list = await client.get("/api/v1/providers")
    assert res_list.status_code == 200
    providers = res_list.json()["data"]
    assert len(providers) >= 6

    # 2. Create new Provider
    res_create = await client.post(
        "/api/v1/providers",
        json={
            "provider_type": "llm",
            "provider_name": "custom",
            "display_name": "My Custom Model",
            "enabled": True,
            "is_default": False,
            "config": {"base_url": "https://api.custom-ai.com/v1", "model": "custom-v1"},
            "credentials": {"api_key": "sk-custom-secret-key-12345"},
        },
    )
    assert res_create.status_code == 201
    created = res_create.json()["data"]
    prov_id = created["id"]
    assert created["display_name"] == "My Custom Model"
    assert created["masked_credentials"]["api_key"] != "sk-custom-secret-key-12345"
    assert "••••" in created["masked_credentials"]["api_key"]

    # 3. Get Detail
    res_get = await client.get(f"/api/v1/providers/{prov_id}")
    assert res_get.status_code == 200
    detail = res_get.json()["data"]
    assert detail["id"] == prov_id
    assert detail["has_credentials"] is True

    # 4. Set Default
    res_default = await client.post(f"/api/v1/providers/{prov_id}/set-default")
    assert res_default.status_code == 200
    assert res_default.json()["data"]["is_default"] is True

    # 5. Toggle Disabled
    res_toggle = await client.post(f"/api/v1/providers/{prov_id}/toggle")
    assert res_toggle.status_code == 200
    assert res_toggle.json()["data"]["enabled"] is False

    # 6. Update
    res_update = await client.put(
        f"/api/v1/providers/{prov_id}",
        json={
            "display_name": "My Custom Model (Renamed)",
            "enabled": True,
            "credentials": {"api_key": "sk-cu••••••••2345"},  # unchanged masked placeholder
        },
    )
    assert res_update.status_code == 200
    assert res_update.json()["data"]["display_name"] == "My Custom Model (Renamed)"

    # 7. Delete
    res_del = await client.delete(f"/api/v1/providers/{prov_id}")
    assert res_del.status_code == 200
    assert res_del.json()["data"] is True

    # 8. Verify 404 after deletion
    res_404 = await client.get(f"/api/v1/providers/{prov_id}")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_system_config_summary_is_aggregated_and_redacted(client: AsyncClient):
    created = await _create_llm_provider(
        client,
        provider_name="summary-test",
        display_name="Summary Test Provider",
        model="summary-model",
        api_key="sk-summary-secret-value",
    )
    provider_id = created["id"]

    response = await client.get("/api/v1/providers/summary")
    assert response.status_code == 200
    summary = response.json()["data"]

    assert {"overall", "system", "storage", "categories", "providers", "publishing"} <= summary.keys()
    assert {item["type"] for item in summary["categories"]} == {
        "llm", "search", "image", "video", "material", "tts", "publishing"
    }
    material = next(item for item in summary["categories"] if item["type"] == "material")
    assert material["label"] == "在线素材"
    llm = next(item for item in summary["categories"] if item["type"] == "llm")
    assert llm["default_provider_id"]
    publishing = next(item for item in summary["categories"] if item["type"] == "publishing")
    assert publishing["configured"] is False
    assert publishing["status"] == "not_configured"
    provider = next(item for item in summary["providers"] if item["id"] == provider_id)
    assert provider["configured"] is True
    assert provider["connection_status"] == "not_tested"
    assert "••••" in provider["masked_credentials"]["api_key"]
    assert "sk-summary-secret-value" not in json.dumps(summary, ensure_ascii=False)
    assert "credentials_encrypted" not in json.dumps(summary, ensure_ascii=False)


@pytest.mark.asyncio
async def test_provider_test_persists_success_and_configuration_changes_clear_it(
    client: AsyncClient, monkeypatch
):
    created = await _create_llm_provider(
        client,
        provider_name="persist-success",
        display_name="Persist Success",
        model="persist-model",
        api_key="sk-persist-success",
    )
    provider_id = created["id"]

    async def fake_test(self, cfg, creds, provider_name=None):
        return ProviderTestResponse(
            connected=True,
            message="连接成功",
            latency_ms=123.4,
        )

    monkeypatch.setattr(ProviderManager, "_test_llm_connection", fake_test)

    tested = await client.post(
        "/api/v1/providers/test",
        json={
            "provider_id": provider_id,
            "provider_type": "llm",
            "provider_name": "persist-success",
            "config": {"base_url": "https://example.invalid/v1", "model": "persist-model"},
            "credentials": {"api_key": "sk-persist-success"},
        },
    )
    assert tested.status_code == 200
    assert tested.json()["data"]["connected"] is True

    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "ready"
    assert provider["last_test"]["connected"] is True
    assert provider["last_test"]["message"] == "连接成功"
    assert provider["last_test"]["latency_ms"] == 123.4
    assert provider["last_test"]["tested_at"]

    # Masked placeholders do not count as a credential change.
    unchanged = await client.put(
        f"/api/v1/providers/{provider_id}",
        json={"credentials": {"api_key": "sk-••••••••cess"}},
    )
    assert unchanged.status_code == 200
    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "ready"

    changed_config = await client.put(
        f"/api/v1/providers/{provider_id}",
        json={"config": {"model": "changed-model"}},
    )
    assert changed_config.status_code == 200
    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "not_tested"
    assert provider["last_test"] is None

    retested = await client.post(f"/api/v1/providers/{provider_id}/test")
    assert retested.status_code == 200
    assert retested.json()["data"]["connected"] is True
    changed_credentials = await client.put(
        f"/api/v1/providers/{provider_id}",
        json={"credentials": {"api_key": "sk-persist-success-rotated"}},
    )
    assert changed_credentials.status_code == 200
    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "not_tested"
    assert provider["last_test"] is None


@pytest.mark.asyncio
async def test_provider_test_persists_failure_and_raw_config_test_is_temporary(
    client: AsyncClient, monkeypatch
):
    created = await _create_llm_provider(
        client,
        provider_name="persist-failure",
        display_name="Persist Failure",
        model="failure-model",
        api_key="sk-persist-failure",
    )
    provider_id = created["id"]

    async def fake_failure(self, cfg, creds, provider_name=None):
        return ProviderTestResponse(
            connected=False,
            message="认证失败",
            latency_ms=45.6,
        )

    monkeypatch.setattr(ProviderManager, "_test_llm_connection", fake_failure)

    failed = await client.post(
        f"/api/v1/providers/{provider_id}/test",
    )
    assert failed.status_code == 200
    assert failed.json()["data"]["connected"] is False

    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "failed"
    assert provider["last_test"]["connected"] is False
    assert provider["last_test"]["message"] == "认证失败"
    assert provider["last_test"]["latency_ms"] == 45.6
    tested_at = provider["last_test"]["tested_at"]

    temporary = await client.post(
        "/api/v1/providers/test",
        json={
            "provider_type": "llm",
            "provider_name": "persist-failure",
            "config": {"base_url": "https://example.invalid/v1", "model": "failure-model"},
            "credentials": {"api_key": "sk-temporary-only"},
        },
    )
    assert temporary.status_code == 200
    assert temporary.json()["data"]["connected"] is False

    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "failed"
    assert provider["last_test"]["tested_at"] == tested_at
    summary = (await client.get("/api/v1/providers/summary")).json()["data"]
    assert "sk-temporary-only" not in json.dumps(summary, ensure_ascii=False)

    dirty = await client.post(
        "/api/v1/providers/test",
        json={
            "provider_id": provider_id,
            "provider_type": "llm",
            "provider_name": "persist-failure",
            "config": {"model": "unsaved-model"},
            "credentials": {"api_key": "sk-unsaved-key"},
        },
    )
    assert dirty.status_code == 200
    assert dirty.json()["data"]["connected"] is False
    provider = await _provider_summary(client, provider_id)
    assert provider["connection_status"] == "failed"
    assert provider["last_test"]["tested_at"] == tested_at
    summary = (await client.get("/api/v1/providers/summary")).json()["data"]
    assert "sk-unsaved-key" not in json.dumps(summary, ensure_ascii=False)


@pytest.mark.asyncio
async def test_provider_test_rejects_missing_or_mismatched_saved_provider(client: AsyncClient):
    missing = await client.post("/api/v1/providers/test", json={"provider_id": "missing-provider"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    mismatch = await client.post(
        "/api/v1/providers/test",
        json={
            "provider_id": "prov_llm_deepseek",
            "provider_type": "search",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_system_config_summary_with_active_publishing_account(
    client: AsyncClient, monkeypatch
):
    async def mock_validate(self, cred):
        return True

    monkeypatch.setattr(DouyinPublishingProvider, "validate_account", mock_validate)

    # 1. Create a valid cookie credential
    cred_res = await client.post(
        "/api/v1/publishing/credentials",
        json={
            "platform": "douyin",
            "credential_type": "cookie",
            "payload": {"cookies": [{"name": "sessionid", "value": "mock_valid_douyin_session"}]},
        },
    )
    assert cred_res.status_code == 201
    cred_id = cred_res.json()["data"]["id"]

    # 2. Create Douyin social account linked to this credential
    acc_res = await client.post(
        "/api/v1/publishing/accounts",
        json={
            "platform": "douyin",
            "account_name": "官方主账号",
            "username": "official_douyin_tester",
            "credential_id": cred_id,
        },
    )
    assert acc_res.status_code == 201
    account_id = acc_res.json()["data"]["id"]

    # 3. Check account credential validity
    check_res = await client.post(f"/api/v1/publishing/accounts/{account_id}/check")
    assert check_res.status_code == 200
    assert check_res.json()["data"]["is_valid"] is True

    # 4. Verify system-config-summary accurately reflects "ready" status
    summary_res = await client.get("/api/v1/providers/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()["data"]

    publishing_category = next(c for c in summary["categories"] if c["type"] == "publishing")
    assert publishing_category["status"] == "ready"
    assert publishing_category["configured"] is True
    assert publishing_category["missing_fields"] == []

    publishing_deck = summary["publishing"]
    assert publishing_deck["status"] == "ready"
    assert publishing_deck["total_accounts"] >= 1
    assert publishing_deck["pending_accounts"] == 0
    assert publishing_deck["invalid_accounts"] == 0

    account_item = next(a for a in publishing_deck["accounts"] if a["id"] == account_id)
    assert account_item["credential_status"] == "ready"
    assert account_item["status"] == "active"
