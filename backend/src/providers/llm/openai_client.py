import json
import re
import socket
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError

from src.core.exceptions import ProviderException
from src.core.security import log_exception_safely, redact_sensitive_text
from src.providers.base import mask_secret, retry_async
from src.providers.llm.defaults import DEFAULT_OPENAI_MODEL
from src.providers.llm.protocol import StructuredOutputException

T = TypeVar("T", bound=BaseModel)


def infer_provider_name(
    provider_name: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> str:
    """Resolve a stable provider identifier for OpenAI-compatible endpoints."""
    explicit_name = (provider_name or "").strip().lower()
    if explicit_name:
        return explicit_name

    endpoint = f"{base_url or ''} {model or ''}".lower()
    if "api.cloudflare.com" in endpoint or "@cf/" in endpoint:
        return "cloudflare"
    if "api.deepseek.com" in endpoint or "deepseek" in endpoint:
        return "deepseek"
    if (
        "api.z.ai" in endpoint
        or "bigmodel.cn" in endpoint
        or "zhipu" in endpoint
        or "glm-" in endpoint
    ):
        return "zai"
    if "11434" in endpoint or "ollama" in endpoint:
        return "ollama"
    return "custom"


def _safe_endpoint_host(base_url: str) -> str:
    """Return only the endpoint host for diagnostics, never its account path."""
    try:
        hostname = urlparse(base_url).hostname
    except ValueError:
        hostname = None
    return hostname or "configured-endpoint"


def _network_error_text(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current).casefold())
        current = current.__cause__ or current.__context__
    return " ".join(parts)


def _network_error_category(exc: BaseException) -> str:
    """Classify retryable transport failures without exposing exception text."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.RemoteProtocolError):
        return "remote_protocol"
    if isinstance(exc, httpx.ConnectError):
        text = _network_error_text(exc)
        if (
            isinstance(exc.__cause__, socket.gaierror)
            or "getaddrinfo" in text
            or "name or service not known" in text
            or "temporary failure in name resolution" in text
            or "11001" in text
        ):
            return "dns_resolution"
        return "connect_error"
    return "network_error"


def _is_forced_reasoning_model(model: str) -> bool:
    normalized_model = (model or "").strip().lower()
    if "gpt-oss" in normalized_model or "qwq" in normalized_model:
        return True
    return bool(re.search(r"(?:^|[/_.:-])o[134](?:$|[/_.:-])", normalized_model))


def _is_ollama_thinking_model(model: str) -> bool:
    normalized_model = (model or "").strip().lower()
    return any(
        marker in normalized_model
        for marker in ("qwen3", "deepseek-r1", "deepseek-reasoner", "reasoning", "think")
    )


def resolve_thinking_controls(
    provider_name: str | None,
    base_url: str | None,
    model: str | None,
    *,
    disable_thinking: bool = True,
) -> tuple[dict[str, Any], str, str | None]:
    """Return provider-specific thinking controls and a safe diagnostic status.

    The returned warning is intentionally descriptive only; it never contains
    model output or credentials.
    """
    if not disable_thinking:
        return {}, "enabled_or_provider_default", None

    normalized_provider = infer_provider_name(provider_name, base_url, model)
    normalized_url = (base_url or "").lower()
    normalized_model = (model or "").lower()

    is_cloudflare = normalized_provider == "cloudflare" or "api.cloudflare.com" in normalized_url
    is_deepseek = normalized_provider == "deepseek" or "api.deepseek.com" in normalized_url
    is_zai = normalized_provider in {"zai", "z.ai", "zhipu", "zhipuai"} or any(
        marker in normalized_url for marker in ("api.z.ai", "bigmodel.cn")
    )
    is_ollama = normalized_provider == "ollama" or "11434" in normalized_url or "ollama" in normalized_url

    if _is_forced_reasoning_model(normalized_model):
        return (
            {"reasoning_effort": "low"},
            "forced_reasoning_low",
            f"模型 {model or '<unknown>'} 无法完全关闭 thinking，已使用最低 reasoning_effort=low。",
        )

    if is_cloudflare and any(
        marker in normalized_model for marker in ("glm", "kimi", "qwen3", "deepseek-r1")
    ):
        return (
            {
                "reasoning_effort": None,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            "cloudflare_disabled",
            None,
        )

    if is_deepseek or is_zai:
        return {"thinking": {"type": "disabled"}}, "thinking_disabled", None

    if is_ollama and _is_ollama_thinking_model(normalized_model):
        return {"reasoning_effort": "none"}, "ollama_disabled", None

    return {}, "not_needed", None


def _content_stats(value: Any) -> tuple[bool, int]:
    """Return presence and character count without exposing the value."""
    if isinstance(value, str):
        return bool(value), len(value)
    if isinstance(value, list):
        text_parts = [
            item.get("text")
            for item in value
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        total_chars = sum(len(part) for part in text_parts)
        return bool(text_parts), total_chars
    if value is None:
        return False, 0
    return True, 0


def extract_chat_completion_content(data: Any) -> str:
    """Extract final content first, with reasoning content as a null fallback."""
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    msg = first_choice.get("message")
    if not isinstance(msg, dict):
        return ""

    raw_content = msg.get("content")
    if raw_content is None:
        raw_content = msg.get("reasoning_content") or ""
    if isinstance(raw_content, str):
        return raw_content.strip()
    if isinstance(raw_content, list):
        text_parts = [
            item.get("text")
            for item in raw_content
            if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("text")
        ]
        return " ".join(text_parts).strip()
    return ""


def _generate_schema_example(schema_class: type[BaseModel]) -> str:
    """Generate a clean JSON data example from a Pydantic model for LLM prompting."""
    try:
        schema = schema_class.model_json_schema()
        defs = schema.get("$defs", {})

        def resolve_node(node: dict) -> Any:
            if not isinstance(node, dict):
                return "<string>"

            if "const" in node:
                return node["const"]
            if node.get("enum"):
                return node["enum"][0]

            default = node.get("default")
            if default not in (None, ""):
                return default

            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                if ref_name in defs:
                    return resolve_node(defs[ref_name])

            for union_key in ("anyOf", "oneOf"):
                branches = node.get(union_key)
                if not isinstance(branches, list):
                    continue
                non_null = [branch for branch in branches if branch.get("type") != "null"]
                if not non_null:
                    return None
                selected = non_null[0]
                # Optional scalar fields with a null default are clearer as null;
                # nested models still need their object shape shown to the LLM.
                if default is None and selected.get("type") in {"string", "number", "integer", "boolean"}:
                    return None
                return resolve_node(selected)

            if isinstance(node.get("allOf"), list) and node["allOf"]:
                return resolve_node(node["allOf"][0])

            prop_type = node.get("type", "string")
            if isinstance(prop_type, list):
                prop_type = next((item for item in prop_type if item != "null"), "string")
            if prop_type == "array":
                return [resolve_node(node.get("items", {}))]
            if prop_type == "integer":
                return 0
            if prop_type == "number":
                return 4.0
            if prop_type == "boolean":
                return True
            if prop_type == "object":
                properties = node.get("properties")
                if isinstance(properties, dict):
                    return {key: resolve_node(value) for key, value in properties.items()}
                return {}

            desc = node.get("description")
            return f"<{desc}>" if desc else "<string>"

        def resolve_obj(obj_schema: dict) -> dict:
            return resolve_node(obj_schema)

        example_dict = resolve_obj(schema)
        return json.dumps(example_dict, ensure_ascii=False, indent=2)
    except Exception:
        return json.dumps(schema_class.model_json_schema(), ensure_ascii=False, indent=2)


def _repair_json_text(value: str) -> str:
    """Repair the small syntax mistakes commonly produced in LLM JSON."""
    repaired: list[str] = []
    in_string = False
    escaped = False

    for index, char in enumerate(value):
        if in_string:
            if escaped:
                repaired.append(char)
                escaped = False
            elif char == "\\":
                repaired.append(char)
                escaped = True
            elif char == '"':
                next_non_space = next(
                    (item for item in value[index + 1 :] if not item.isspace()), None
                )
                if next_non_space is not None and next_non_space not in ",}]:":
                    repaired.append('\\"')
                else:
                    repaired.append(char)
                    in_string = False
            else:
                repaired.append(char)
        else:
            repaired.append(char)
            if char == '"':
                in_string = True

    result = "".join(repaired)
    result = re.sub(r",\s*([}\]])", r"\1", result)
    result = re.sub(r'([}\]])\s*(?=")', r"\1,", result)
    return result


def _parse_json_response(raw_response: str) -> Any | None:
    """Extract a JSON value from plain, fenced, or lightly malformed LLM text."""
    if not isinstance(raw_response, str) or not raw_response.strip():
        return None

    text = raw_response.strip().lstrip("\ufeff")
    candidates: list[str] = []
    code_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidates.extend(code_matches)
    candidates.append(text)

    seen_candidates: set[str] = set()
    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)
        variants = [candidate, _repair_json_text(candidate)]
        seen_variants: set[str] = set()
        for variant in variants:
            if not variant or variant in seen_variants:
                continue
            seen_variants.add(variant)
            try:
                return json.loads(variant)
            except json.JSONDecodeError:
                pass

            match = re.search(r"[\[{]", variant)
            if match:
                try:
                    parsed, _ = decoder.raw_decode(variant[match.start() :])
                    return parsed
                except json.JSONDecodeError:
                    pass

    return None


class OpenAICompatibleLLMProvider:
    """Universal OpenAI-compatible LLM client (OpenAI, DashScope/Qwen, DeepSeek, Ollama, SiliconFlow)"""

    name = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float = 120.0,
        provider_name: str | None = None,
        supports_native_json_schema: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.provider_name = infer_provider_name(provider_name, self.base_url, self.model)
        self.supports_native_json_schema = supports_native_json_schema is True
        self._thinking_warning_emitted = False
        self.last_usage: dict | None = None
        self.last_structured_repair_count = 0
        self.last_structured_native_json_schema = False

    def _build_payload(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        disable_thinking: bool = True,
        response_format: dict | None = None,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        thinking_fields, thinking_strategy, thinking_warning = resolve_thinking_controls(
            self.provider_name,
            self.base_url,
            self.model,
            disable_thinking=disable_thinking,
        )
        payload.update(thinking_fields)
        self._last_thinking_strategy = thinking_strategy
        if thinking_warning and not self._thinking_warning_emitted:
            logger.warning(thinking_warning)
            self._thinking_warning_emitted = True
        return payload

    def _extract_content(self, data: dict) -> str:
        return extract_chat_completion_content(data)

    def _log_response_diagnostics(self, data: Any) -> None:
        """Log response shape only; never log the model output itself."""
        finish_reason: Any = None
        content: Any = None
        reasoning_content: Any = None
        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            first_choice = choices[0]
            finish_reason = first_choice.get("finish_reason")
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                reasoning_content = message.get("reasoning_content")

        if isinstance(finish_reason, str):
            finish_reason = finish_reason[:64]
        elif not isinstance(finish_reason, (int, float, bool)) and finish_reason is not None:
            finish_reason = type(finish_reason).__name__
        content_present, content_chars = _content_stats(content)
        reasoning_present, reasoning_chars = _content_stats(reasoning_content)
        strategy = getattr(self, "_last_thinking_strategy", "unknown")
        logger.info(
            f"LLM response diagnostics: finish_reason={finish_reason!r}, "
            f"content_present={content_present}, content_chars={content_chars}, "
            f"reasoning_content_present={reasoning_present}, reasoning_content_chars={reasoning_chars}, "
            f"thinking_strategy={strategy}"
        )

    @retry_async(
        max_retries=2,
        exceptions=(httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException),
        retry_log_level="info",
        error_formatter=_network_error_category,
    )
    async def _post_chat_completion(
        self, client: httpx.AsyncClient, payload: dict, headers: dict
    ) -> httpx.Response:
        return await client.post(
            f"{self.base_url}/chat/completions",
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
        self.last_usage = None
        if not self.api_key:
            raise ProviderException(self.name, "LLM API key is not configured.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint_host = _safe_endpoint_host(self.base_url)

        logger.info(
            f"LLM request to {endpoint_host} [model={self.model}, key={mask_secret(self.api_key)}]"
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, trust_env=False
            ) as client:
                res = await self._post_chat_completion(client, payload, headers)
                res.raise_for_status()
                data = res.json()
                usage = data.get("usage") if isinstance(data, dict) else None
                self.last_usage = usage if isinstance(usage, dict) else None
                self._log_response_diagnostics(data)
                return self._extract_content(data)
        except ProviderException:
            raise
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else "unknown"
            err_body = redact_sensitive_text(e.response.text[:500]) if e.response else ""
            log_exception_safely(
                logger,
                f"LLM HTTP error ({endpoint_host}, {self.model}): {status_code} - {err_body}",
                e,
            )
            raise ProviderException(
                self.name, f"LLM API 接口返回 HTTP {status_code}: {err_body}"
            ) from e
        except httpx.RequestError as e:
            category = _network_error_category(e)
            if category == "remote_protocol":
                err_msg = "大模型服务器在返回响应前关闭了连接（已重试），请检查 Cloudflare 网络连通性或 API Token。"
            elif category == "timeout":
                err_msg = f"请求大模型服务超时 ({self.timeout_seconds:.0f}s)，请检查网络或网关地址。"
            elif category == "dns_resolution":
                err_msg = f"无法解析大模型服务器地址 ({endpoint_host})，请检查 DNS 或网络配置。"
            elif category == "connect_error":
                err_msg = f"无法连接到大模型服务器 ({endpoint_host})，请检查网络或网关地址。"
            else:
                err_msg = "大模型网络请求失败，请检查网络或网关地址。"
            safe_err_msg = f"{err_msg} [category={category}, endpoint={endpoint_host}]"
            logger.error(f"LLM request to {endpoint_host} failed: category={category}")
            raise ProviderException(self.name, f"大模型生成失败: {safe_err_msg}") from e
        except Exception as e:
            err_type = type(e).__name__
            err_str = redact_sensitive_text(str(e).strip())
            err_msg = f"{err_type}: {err_str}" if err_str else err_type
            log_exception_safely(
                logger,
                f"LLM request to {endpoint_host} failed: {err_msg}",
                e,
            )
            raise ProviderException(self.name, f"大模型生成失败: {err_msg}") from e

    async def generate_structured(
        self,
        prompt: str,
        schema_class: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 6000,
    ) -> T:
        self.last_structured_repair_count = 0
        self.last_structured_native_json_schema = bool(self.supports_native_json_schema)
        example_json = _generate_schema_example(schema_class)
        enhanced_system = (
            (system_prompt or "你是一名专业的结构化短视频编剧导演。")
            + "\n\n【关键要求】你必须直接返回符合以下字段结构的合法 JSON 数据对象（严禁输出 markdown 代码块、```json 标记、额外注释，切勿原样输出 Schema 字段定义或包含 $defs/properties）：\n"
            + example_json
        )

        response_format = None
        if self.supports_native_json_schema:
            schema_name = re.sub(r"[^a-zA-Z0-9_]+", "_", schema_class.__name__).strip("_").lower()
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name or "structured_output",
                    "strict": True,
                    "schema": schema_class.model_json_schema(),
                },
            }
        text_kwargs = {
            "prompt": prompt,
            "system_prompt": enhanced_system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            text_kwargs["response_format"] = response_format
        raw_response = await self.generate_text(**text_kwargs)

        # Parse JSON and validate.  Providers often add a short preamble,
        # markdown fences, or a trailing comma even when asked for JSON only.
        parsed_dict = _parse_json_response(raw_response)

        # Check if the LLM mistakenly echoed the schema definition ($defs / properties)
        is_schema_echo = isinstance(parsed_dict, dict) and ("$defs" in parsed_dict or "properties" in parsed_dict)

        validation_error = ""
        if parsed_dict is not None and not is_schema_echo:
            try:
                return schema_class.model_validate(parsed_dict)
            except ValidationError as val_err:
                validation_error = redact_sensitive_text(
                    json.dumps(
                        val_err.errors(include_input=False, include_url=False),
                        ensure_ascii=False,
                    ),
                    limit=1200,
                )
                logger.warning(
                    f"Initial Pydantic validation failed: {validation_error}. "
                    "Retrying self-correction pass..."
                )

        # Self-correction retry pass
        self.last_structured_repair_count = 1
        repair_reason = "schema validation failure" if validation_error else "malformed JSON or echoed schema"
        logger.warning(
            f"LLM structured output requires self-repair (reason={repair_reason}, "
            f"is_schema_echo={is_schema_echo}). Executing self-repair pass..."
        )
        safe_prompt = redact_sensitive_text(prompt, limit=4000)
        safe_failed_output = redact_sensitive_text(raw_response, limit=4000)
        repair_instruction = (
            "【注意】：你刚才返回的是可解析的 JSON 数据实体，但字段值未通过 schema 校验。"
            "请根据具体校验错误修正字段类型和枚举值。"
            if validation_error
            else "【注意】：你刚才返回的结果不是可校验的 JSON 实体，可能包含 Schema 元数据或 JSON 语法错误。"
        )
        correction_prompt = (
            f"原始任务（已截断和脱敏）:\n{safe_prompt}\n\n"
            f"失败输出（已截断和脱敏）:\n{safe_failed_output}\n\n"
            f"具体校验错误（已截断和脱敏）:\n{validation_error or 'JSON 无法解析或返回了 Schema 定义'}\n\n"
            f"{repair_instruction}\n"
            "请不要返回任何 $defs 或 properties 定义，修正语法并返回包含具体创作内容的 JSON 实体对象。示例：\n"
            + example_json
        )
        retry_kwargs = {
            "prompt": correction_prompt,
            "system_prompt": "你必须严格返回纯 JSON 数据实体，填充实际创作内容，不要包含 $defs 或 properties。",
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            retry_kwargs["response_format"] = response_format
        retry_raw = await self.generate_text(**retry_kwargs)
        try:
            retry_dict = _parse_json_response(retry_raw)
            if not isinstance(retry_dict, dict):
                raise ValueError("LLM 未返回 JSON 数据对象。")
            if "$defs" in retry_dict or "properties" in retry_dict:
                raise ValueError("LLM 返回了 JSON Schema 定义而非数据对象。")
            return schema_class.model_validate(retry_dict)
        except Exception as retry_err:
            safe_retry_error = redact_sensitive_text(str(retry_err).strip(), limit=500)
            raise StructuredOutputException(
                f"LLM 结构化生成数据校验失败: {safe_retry_error or type(retry_err).__name__}"
            ) from retry_err
