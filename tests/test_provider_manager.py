import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import secret_cipher
from src.providers.image.comfyui_image import ComfyUIImageProvider
from src.providers.llm.anthropic import AnthropicLLMProvider
from src.providers.tts.edge_tts import EdgeTTSProvider
from src.schemas.provider import ProviderConfigCreate, ProviderConfigUpdate
from src.services.provider_bootstrap import bootstrap_default_providers
from src.services.provider_manager import ProviderManager


@pytest.mark.asyncio
async def test_provider_bootstrap_and_manager(test_session: AsyncSession):
    # 1. Already bootstrapped by fixture, running again should be a no-op
    assert await bootstrap_default_providers(test_session) is False

    manager = ProviderManager(test_session)

    # 2. List all bootstrapped providers
    all_providers = await manager.list_providers()
    assert len(all_providers) >= 6

    types = {p.provider_type for p in all_providers}
    assert {"llm", "search", "tts", "image", "video", "publishing"}.issubset(types)

    # Verify credentials are masked in response DTO
    for p in all_providers:
        for v in p.masked_credentials.values():
            assert "sk-" not in v or "••••" in v

    # 3. Get Default Instances
    edge_tts = await manager.get_tts()
    assert isinstance(edge_tts, EdgeTTSProvider)

    comfy_img = await manager.get_image()
    assert isinstance(comfy_img, ComfyUIImageProvider)


@pytest.mark.asyncio
async def test_provider_manager_crud_and_encryption(test_session: AsyncSession):
    manager = ProviderManager(test_session)
    seeded_claude = await manager.repo.get_by_name("llm", "claude")
    if seeded_claude:
        await manager.delete_provider(seeded_claude.id)

    # 1. Create a new Claude LLM Provider with plaintext key
    created = await manager.create_provider(
        ProviderConfigCreate(
            provider_type="llm",
            provider_name="claude",
            display_name="Claude Sonnet 5",
            enabled=True,
            is_default=True,
            config={"base_url": "https://api.anthropic.com/v1", "model": "claude-sonnet-5"},
            credentials={"api_key": "sk-ant-testkey1234567890abcdef"},
        )
    )
    assert created.id is not None
    assert created.is_default is True
    assert "sk-ant-testkey" not in created.masked_credentials["api_key"]
    assert "••••" in created.masked_credentials["api_key"]

    # Verify directly in SQLite that it's encrypted
    db_row = await manager.repo.get_by_id(created.id)
    assert db_row is not None
    assert "sk-ant-testkey1234567890abcdef" not in (db_row.credentials_encrypted or "")
    decrypted = secret_cipher.decrypt_dict(db_row.credentials_encrypted)
    assert decrypted["api_key"] == "sk-ant-testkey1234567890abcdef"

    # 2. Get LLM Instance
    llm_instance = await manager.get_llm(created.id)
    assert isinstance(llm_instance, AnthropicLLMProvider)
    assert llm_instance.api_key == "sk-ant-testkey1234567890abcdef"
    assert llm_instance.model == "claude-sonnet-5"
    assert llm_instance.provider_name == "claude"

    # 3. Update without modifying masked key -> keeps existing decrypted key
    updated = await manager.update_provider(
        created.id,
        ProviderConfigUpdate(
            display_name="Claude Sonnet 3.5 (Updated)",
            credentials={"api_key": "sk-an••••••••cdef"},  # masked string submitted by frontend
        ),
    )
    assert updated.display_name == "Claude Sonnet 3.5 (Updated)"

    db_row_updated = await manager.repo.get_by_id(created.id)
    decrypted_again = secret_cipher.decrypt_dict(db_row_updated.credentials_encrypted)
    assert decrypted_again["api_key"] == "sk-ant-testkey1234567890abcdef"

    # 4. Unchecking the default checkbox must actually clear the default flag.
    cleared_default = await manager.update_provider(
        created.id,
        ProviderConfigUpdate(is_default=False),
    )
    assert cleared_default.is_default is False

    # 5. Delete provider
    await manager.delete_provider(created.id)
    assert await manager.repo.get_by_id(created.id) is None


@pytest.mark.asyncio
async def test_provider_manager_test_llm_connection(test_session: AsyncSession, monkeypatch):
    import httpx

    manager = ProviderManager(test_session)
    cfg = {"base_url": "https://api.openai.com/v1", "model": "deepseek-r1"}
    creds = {"api_key": "sk-mock-key"}
    created_clients = []

    class MockAsyncClient:
        def __init__(self, response_factory, *args, **kwargs):
            self.response_factory = response_factory
            self.kwargs = kwargs
            self.last_json = None
            created_clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            self.last_json = json
            return self.response_factory(url, json, headers)

    # 1. Test reasoning model (content is None, reasoning_content present)
    def resp_reasoning(url, json, headers):
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "reasoning_content": "Thinking completed: Ready to answer.",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: MockAsyncClient(resp_reasoning, *args, **kwargs),
    )
    res = await manager._test_llm_connection(cfg, creds)
    assert res.connected is True
    assert res.details["reply"] == "Thinking completed: Ready to answer."
    assert created_clients[-1].kwargs["trust_env"] is False
    assert created_clients[-1].last_json["thinking"] == {"type": "disabled"}

    # Gateway errors and empty replies are the remaining manager-level failure
    # shapes; detailed content extraction is covered by the provider contract tests.
    cases = (
        ({"error": {"message": "Monthly quota exceeded"}}, "Monthly quota exceeded"),
        ({"error": "Custom gateway error"}, "Custom gateway error"),
        ({"detail": "Unauthorized token"}, "Unauthorized token"),
        ({"choices": None}, "空内容"),
        ({"choices": [None]}, "空内容"),
        (
            {"choices": [{"message": {"content": None, "reasoning_content": None}}]},
            "空内容",
        ),
    )
    for body, expected_message in cases:
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *args, _body=body, **kwargs: MockAsyncClient(
                lambda url, json, headers: httpx.Response(
                    status_code=200,
                    json=_body,
                    request=httpx.Request("POST", url),
                ),
                *args,
                **kwargs,
            ),
        )
        result = await manager._test_llm_connection(cfg, creds)
        assert result.connected is False
        assert expected_message in result.message

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: MockAsyncClient(
            lambda url, json, headers: httpx.Response(
                status_code=200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": [{"type": "text", "text": "List response."}],
                            }
                        }
                    ]
                },
                request=httpx.Request("POST", url),
            ),
            *args,
            **kwargs,
        ),
    )
    result = await manager._test_llm_connection(cfg, creds)
    assert result.connected is True
    assert result.details["reply"] == "List response."
