"""Native Anthropic Messages API client.

Anthropic's first-party endpoint is not an OpenAI Chat Completions endpoint.  Keep
it separate from the OpenAI-compatible client so the settings preset exercises the
same protocol that production generation uses.
"""

from typing import Any

import httpx
from loguru import logger

from src.core.exceptions import ProviderException
from src.core.security import log_exception_safely, redact_sensitive_text
from src.providers.base import mask_secret, retry_async
from src.providers.llm.defaults import default_llm_model
from src.providers.llm.openai_client import (
    OpenAICompatibleLLMProvider,
    _network_error_category,
    _safe_endpoint_host,
)


class AnthropicLLMProvider(OpenAICompatibleLLMProvider):
    """LLM provider using Anthropic's native ``/messages`` API."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        model: str | None = None,
        timeout_seconds: float = 120.0,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model or default_llm_model("claude"),
            timeout_seconds=timeout_seconds,
            provider_name="claude",
            supports_native_json_schema=False,
        )

    @staticmethod
    def _extract_content(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        content = data.get("content")
        if not isinstance(content, list):
            return ""
        parts = [
            item.get("text")
            for item in content
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ]
        return "\n".join(part for part in parts if part).strip()

    @retry_async(
        max_retries=2,
        exceptions=(httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException),
        retry_log_level="info",
        error_formatter=_network_error_category,
    )
    async def _post_messages(
        self, client: httpx.AsyncClient, payload: dict, headers: dict[str, str]
    ) -> httpx.Response:
        return await client.post(
            f"{self.base_url}/messages",
            json=payload,
            headers=headers,
        )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: dict | None = None,
    ) -> str:
        del temperature, response_format
        self.last_usage = None
        if not self.api_key:
            raise ProviderException(self.name, "LLM API key is not configured.")

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        endpoint_host = _safe_endpoint_host(self.base_url)
        logger.info(
            f"Anthropic request to {endpoint_host} [model={self.model}, key={mask_secret(self.api_key)}]"
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, trust_env=False
            ) as client:
                response = await self._post_messages(client, payload, headers)
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage") if isinstance(data, dict) else None
                self.last_usage = usage if isinstance(usage, dict) else None
                content = self._extract_content(data)
                logger.info(
                    f"Anthropic response diagnostics: content_present={bool(content)}, "
                    f"content_chars={len(content)}"
                )
                return content
        except ProviderException:
            raise
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response else "unknown"
            error_body = redact_sensitive_text(exc.response.text[:500]) if exc.response else ""
            log_exception_safely(
                logger,
                f"Anthropic HTTP error ({endpoint_host}, {self.model}): "
                f"{status_code} - {error_body}",
                exc,
            )
            raise ProviderException(
                self.name, f"Anthropic API 接口返回 HTTP {status_code}: {error_body}"
            ) from exc
        except httpx.RequestError as exc:
            category = _network_error_category(exc)
            if category == "remote_protocol":
                message = "Anthropic 服务器在返回响应前关闭了连接（已重试）。"
            elif category == "timeout":
                message = f"Anthropic 请求超时 ({self.timeout_seconds:.0f}s)。"
            elif category == "dns_resolution":
                message = f"无法解析 Anthropic 服务器地址 ({endpoint_host})。"
            else:
                message = f"无法连接到 Anthropic 服务器 ({endpoint_host})。"
            raise ProviderException(
                self.name,
                f"大模型生成失败: {message} [category={category}, endpoint={endpoint_host}]",
            ) from exc
        except Exception as exc:
            error_type = type(exc).__name__
            error_text = redact_sensitive_text(str(exc).strip())
            safe_message = f"{error_type}: {error_text}" if error_text else error_type
            log_exception_safely(
                logger,
                f"Anthropic request to {endpoint_host} failed: {safe_message}",
                exc,
            )
            raise ProviderException(self.name, f"大模型生成失败: {safe_message}") from exc
