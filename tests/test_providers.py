import json

import pytest

from src.schemas.generation import StructuredScript


@pytest.mark.asyncio
async def test_openai_structured_output_repairs_json_and_empty_custom_params(monkeypatch):
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    response = {
        "title": "测试标题",
        "hook": "先看一个关键事实",
        "narration": "这是一段测试旁白。",
        "scenes": [
            {
                "sequence_index": 0,
                "narration_text": "这是第一段旁白。",
                "visual_prompt": "干净简洁的测试场景，主体清晰，光线柔和",
                "duration_seconds": 4,
            }
        ],
        "metadata": {"title": "测试标题", "platform_custom_params": ""},
    }
    raw_json = json.dumps(response, ensure_ascii=False).replace(
        "这是一段测试旁白。", '这是一段"测试"旁白。'
    )
    raw_response = "模型说明：\n```json\n" + raw_json[:-1] + ",}\n```"

    provider = OpenAICompatibleLLMProvider(api_key="mock-key")
    async def fake_generate_text(**kwargs):
        return raw_response

    monkeypatch.setattr(provider, "generate_text", fake_generate_text)

    script = await provider.generate_structured("hello", StructuredScript)

    assert script.metadata.platform_custom_params == {}


@pytest.mark.asyncio
async def test_provider_registry_unconfigured_validation():
    from src.core.exceptions import ValidationException
    from src.providers.registry import ProviderRegistry

    # Create fresh registry with no keys
    reg = ProviderRegistry()
    reg.reload_from_config(
        openai_api_key="",
        comfyui_base_url="",
        tavily_api_key="",
    )

    assert reg.is_llm_configured is False
    assert reg.is_image_configured is False
    assert reg.is_video_configured is False
    assert reg.is_search_configured is False

    with pytest.raises(ValidationException) as exc_llm:
        _ = reg.llm
    assert "未配置大语言模型 API Key" in str(exc_llm.value)

    with pytest.raises(ValidationException) as exc_img:
        _ = reg.image
    assert "未配置文生图服务" in str(exc_img.value)

    with pytest.raises(ValidationException) as exc_vid:
        _ = reg.video
    assert "未配置文生视频服务" in str(exc_vid.value)


def test_openai_compatible_llm_extract_content():
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    client = OpenAICompatibleLLMProvider(api_key="mock-key")

    # 1. Standard text content
    standard_data = {
        "choices": [
            {"message": {"role": "assistant", "content": "  Hello World!  "}}
        ]
    }
    assert client._extract_content(standard_data) == "Hello World!"

    both_content_data = {
        "choices": [
            {
                "message": {
                    "content": '{"queries":["最终查询"]}',
                    "reasoning_content": "内部推理，不应交给查询解析器",
                }
            }
        ]
    }
    assert client._extract_content(both_content_data) == '{"queries":["最终查询"]}'

    # 2. Reasoning model (DeepSeek-R1, o1, o3, etc.) where content is None and reasoning_content is present
    reasoning_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "Step 1: Analyzed prompt.\nStep 2: Done.",
                }
            }
        ]
    }
    assert client._extract_content(reasoning_data) == "Step 1: Analyzed prompt.\nStep 2: Done."

    # 3. Both content and reasoning_content are None / empty
    empty_content_data = {
        "choices": [
            {"message": {"role": "assistant", "content": None, "reasoning_content": None}}
        ]
    }
    assert client._extract_content(empty_content_data) == ""

    # 4. List of structured/multimodal content parts
    list_content_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Part 1."},
                        {"type": "text", "text": "Part 2."},
                    ],
                }
            }
        ]
    }
    assert client._extract_content(list_content_data) == "Part 1. Part 2."

    # 5. Defensive cases for malformed/gateway structures
    assert client._extract_content({}) == ""
    assert client._extract_content({"choices": None}) == ""
    assert client._extract_content({"choices": []}) == ""
    assert client._extract_content({"choices": [None]}) == ""
    assert client._extract_content({"choices": [{}]}) == ""
    assert client._extract_content({"choices": [{"message": None}]}) == ""
    assert client._extract_content(None) == ""
    assert client._extract_content("invalid") == ""


@pytest.mark.asyncio
async def test_anthropic_provider_uses_native_messages_protocol(monkeypatch):
    import httpx

    from src.providers.llm.anthropic import AnthropicLLMProvider

    requests = []

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            requests.append((url, json, headers))
            return httpx.Response(
                status_code=200,
                json={
                    "content": [{"type": "text", "text": "Native response."}],
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                },
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    provider = AnthropicLLMProvider(
        api_key="sk-ant-test",
        base_url="https://api.anthropic.com/v1",
        model="claude-sonnet-5",
    )

    result = await provider.generate_text(
        "hello",
        system_prompt="Be concise.",
        temperature=0.0,
        max_tokens=12,
    )

    assert result == "Native response."
    assert provider.last_usage == {"input_tokens": 3, "output_tokens": 2}
    url, payload, headers = requests[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert payload == {
        "model": "claude-sonnet-5",
        "max_tokens": 12,
        "messages": [{"role": "user", "content": "hello"}],
        "system": "Be concise.",
    }
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "Authorization" not in headers


def test_openai_compatible_llm_builds_provider_thinking_controls():
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    messages = [{"role": "user", "content": "hello"}]

    cloudflare = OpenAICompatibleLLMProvider(
        api_key="mock-key",
        base_url="https://api.cloudflare.com/client/v4/account/ai/v1",
        model="@cf/zai-org/glm-4.7-flash",
        provider_name="cloudflare",
    )
    cloudflare_payload = cloudflare._build_payload(messages)
    assert cloudflare_payload["reasoning_effort"] is None
    assert cloudflare_payload["chat_template_kwargs"] == {"enable_thinking": False}

    deepseek = OpenAICompatibleLLMProvider(
        api_key="mock-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-flash",
        provider_name="deepseek",
    )
    assert deepseek._build_payload(messages)["thinking"] == {"type": "disabled"}

    zai = OpenAICompatibleLLMProvider(
        api_key="mock-key",
        base_url="https://api.z.ai/api/paas/v4",
        model="glm-4.7",
        provider_name="zai",
    )
    assert zai._build_payload(messages)["thinking"] == {"type": "disabled"}

    ollama = OpenAICompatibleLLMProvider(
        api_key="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3:8b",
        provider_name="ollama",
    )
    assert ollama._build_payload(messages)["reasoning_effort"] == "none"

    ollama_plain = OpenAICompatibleLLMProvider(
        api_key="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="llama3.2",
        provider_name="ollama",
    )
    ollama_plain_payload = ollama_plain._build_payload(messages)
    assert "reasoning_effort" not in ollama_plain_payload

    forced = OpenAICompatibleLLMProvider(
        api_key="mock-key",
        model="o3-mini",
        provider_name="openai",
    )
    assert forced._build_payload(messages)["reasoning_effort"] == "low"

    ordinary = OpenAICompatibleLLMProvider(
        api_key="mock-key",
        model="gpt-5.6-luna",
        provider_name="openai",
    )
    ordinary_payload = ordinary._build_payload(messages)
    assert "reasoning_effort" not in ordinary_payload
    assert "thinking" not in ordinary_payload


def test_provider_registry_passes_llm_provider_name():
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider
    from src.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    registry.reload_from_config(
        openai_api_key="mock-key",
        openai_base_url="https://api.cloudflare.com/client/v4/account/ai/v1",
        openai_model="@cf/zai-org/glm-4.7-flash",
        openai_provider_name="cloudflare",
        comfyui_base_url="",
        tavily_api_key="",
    )

    assert isinstance(registry.llm, OpenAICompatibleLLMProvider)
    assert registry.llm.provider_name == "cloudflare"
    assert registry.llm._build_payload([])["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_openai_compatible_llm_retries_remote_disconnect(monkeypatch):
    import httpx
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    sleep_delays = []

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr("src.providers.base.asyncio.sleep", fake_sleep)

    class MockAsyncClient:
        calls = 0

        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            self.calls += 1
            if self.calls == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return httpx.Response(
                status_code=200,
                json={"choices": [{"message": {"content": "Recovered"}}]},
                request=httpx.Request("POST", url),
            )

    created_clients = []

    def create_client(*args, **kwargs):
        client = MockAsyncClient(*args, **kwargs)
        created_clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", create_client)

    provider = OpenAICompatibleLLMProvider(api_key="mock-key")

    assert await provider.generate_text("hello") == "Recovered"
    assert created_clients[-1].calls == 2
    assert sleep_delays == [1.0]
    assert created_clients[-1].kwargs["trust_env"] is False


@pytest.mark.asyncio
async def test_openai_compatible_llm_retries_dns_without_warning(monkeypatch):
    import httpx
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    class CapturedLogger:
        def __init__(self):
            self.events = []

        def info(self, message):
            self.events.append(("info", str(message)))

        def warning(self, message):
            self.events.append(("warning", str(message)))

        def error(self, message):
            self.events.append(("error", str(message)))

    captured_logger = CapturedLogger()
    monkeypatch.setattr("src.providers.base.logger", captured_logger)
    monkeypatch.setattr("src.providers.llm.openai_client.logger", captured_logger)

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("src.providers.base.asyncio.sleep", fake_sleep)

    class MockAsyncClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            self.calls += 1
            if self.calls == 1:
                raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
            return httpx.Response(
                status_code=200,
                json={"choices": [{"message": {"content": "Recovered"}}]},
                request=httpx.Request("POST", url),
            )

    mock_client = MockAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client)

    provider = OpenAICompatibleLLMProvider(
        api_key="secret-api-key",
        base_url="https://api.cloudflare.com/client/v4/accounts/secret-account/ai/v1",
        model="@cf/zai-org/glm-4.7-flash",
        provider_name="cloudflare",
    )

    assert await provider.generate_text("hello") == "Recovered"
    retry_events = [event for event in captured_logger.events if "retrying" in event[1]]
    assert len(retry_events) == 1
    assert retry_events[0][0] == "info"
    assert "dns_resolution" in retry_events[0][1]
    assert not any(level == "warning" for level, _ in retry_events)
    assert all("secret-account" not in message for _, message in captured_logger.events)
    assert all("secret-api-key" not in message for _, message in captured_logger.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure_kind", "expected_message"),
    [("dns", "dns_resolution"), ("remote", "服务器在返回响应前关闭了连接")],
)
async def test_openai_compatible_llm_reports_terminal_transport_errors(
    monkeypatch, failure_kind, expected_message
):
    import httpx
    from src.core.exceptions import ProviderException
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    class CapturedLogger:
        def __init__(self):
            self.events = []

        def info(self, message):
            self.events.append(("info", str(message)))

        def error(self, message):
            self.events.append(("error", str(message)))

    captured_logger = CapturedLogger()
    monkeypatch.setattr("src.providers.base.logger", captured_logger)
    monkeypatch.setattr("src.providers.llm.openai_client.logger", captured_logger)

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("src.providers.base.asyncio.sleep", fake_sleep)

    class MockAsyncClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            self.calls += 1
            if failure_kind == "dns":
                raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    mock_client = MockAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client)

    provider = OpenAICompatibleLLMProvider(
        api_key="secret-api-key",
        base_url="https://api.cloudflare.com/client/v4/accounts/secret-account/ai/v1",
        model="@cf/zai-org/glm-4.7-flash",
        provider_name="cloudflare",
    )

    with pytest.raises(ProviderException, match=expected_message):
        await provider.generate_text("hello")

    assert mock_client.calls == 2
    messages = [message for _, message in captured_logger.events]
    assert any(level == "error" for level, _ in captured_logger.events)
    assert all("secret-account" not in message for message in messages)
    assert all("secret-api-key" not in message for message in messages)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_message"),
    [(401, "invalid token"), (400, "unsupported thinking parameter")],
)
async def test_openai_compatible_llm_does_not_retry_http_errors(
    monkeypatch, status_code, error_message
):
    import httpx
    from src.core.exceptions import ProviderException
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    sleep_delays = []

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr("src.providers.base.asyncio.sleep", fake_sleep)

    class MockAsyncClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            self.calls += 1
            return httpx.Response(
                status_code=status_code,
                json={"error": {"message": error_message}},
                request=httpx.Request("POST", url),
            )

    mock_client = MockAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: mock_client)

    provider = OpenAICompatibleLLMProvider(api_key="mock-key")

    with pytest.raises(ProviderException, match=rf"HTTP {status_code}"):
        await provider.generate_text("hello")

    assert mock_client.calls == 1
    assert sleep_delays == []


@pytest.mark.asyncio
async def test_openai_compatible_llm_redacts_credentials_from_http_errors(monkeypatch):
    import httpx
    from src.core.exceptions import ProviderException
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider

    class CapturedLogger:
        def __init__(self):
            self.messages = []
            self.options = {}

        def info(self, message):
            self.messages.append(str(message))

        def opt(self, **kwargs):
            self.options.update(kwargs)
            return self

        def error(self, message):
            self.messages.append(str(message))

    captured_logger = CapturedLogger()
    monkeypatch.setattr("src.providers.llm.openai_client.logger", captured_logger)

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None, headers=None):
            return httpx.Response(
                status_code=500,
                text="Authorization: Bearer test-api-token-secret",
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: MockAsyncClient())

    provider = OpenAICompatibleLLMProvider(api_key="test-api-token-secret")

    with pytest.raises(ProviderException) as exc_info:
        await provider.generate_text("hello")

    assert "test-api-token-secret" not in str(exc_info.value)
    assert all("test-api-token-secret" not in message for message in captured_logger.messages)
    assert captured_logger.options["diagnose"] is False


@pytest.mark.asyncio
async def test_openai_structured_validation_error_uses_internal_exception(monkeypatch):
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider
    from src.providers.llm.protocol import StructuredOutputException
    from src.schemas.generation import StructuredScript

    responses = iter(["not valid JSON", "still not valid JSON"])

    async def fake_generate_text(*args, **kwargs):
        return next(responses)

    provider = OpenAICompatibleLLMProvider(api_key="mock-key")
    monkeypatch.setattr(provider, "generate_text", fake_generate_text)

    with pytest.raises(StructuredOutputException, match="结构化生成数据校验失败"):
        await provider.generate_structured("hello", StructuredScript)


@pytest.mark.asyncio
async def test_openai_structured_repair_prompt_is_targeted_and_redacted(monkeypatch):
    from src.providers.llm.openai_client import OpenAICompatibleLLMProvider
    from src.providers.llm.protocol import StructuredOutputException
    from src.schemas.generation import StructuredScript

    secret = "super-secret-token"
    signed = "https://cdn.test/video.mp4?X-Amz-Signature=signed-secret-value"
    calls = []

    async def fake_generate_text(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return '{"title":"标题","scenes":[],"Authorization":"Bearer ' + secret + '","url":"' + signed + '"}'
        return "still not valid JSON"

    provider = OpenAICompatibleLLMProvider(api_key="mock-key")
    monkeypatch.setattr(provider, "generate_text", fake_generate_text)

    with pytest.raises(StructuredOutputException):
        await provider.generate_structured("原始任务 token=" + secret, StructuredScript)

    repair_prompt = calls[1]["prompt"]
    assert "失败输出（已截断和脱敏）" in repair_prompt
    assert "具体校验错误（已截断和脱敏）" in repair_prompt
    assert secret not in repair_prompt
    assert "signed-secret-value" not in repair_prompt
    assert "[REDACTED]" in repair_prompt
