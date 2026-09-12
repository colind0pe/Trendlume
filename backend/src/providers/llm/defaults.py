"""Canonical defaults for the built-in language-model Provider presets."""

from typing import Final

DEFAULT_OPENAI_MODEL: Final = "gpt-5.6-luna"

DEFAULT_LLM_MODELS: Final[dict[str, str]] = {
    "deepseek": "deepseek-v4-flash",
    "openai": DEFAULT_OPENAI_MODEL,
    "claude": "claude-sonnet-5",
    "anthropic": "claude-sonnet-5",
    "cloudflare": "@cf/openai/gpt-oss-120b",
    "ollama": "qwen3:8b",
    "custom": DEFAULT_OPENAI_MODEL,
    "custom_llm": DEFAULT_OPENAI_MODEL,
}


def default_llm_model(provider_name: str | None) -> str:
    """Return the safe built-in model for a provider or OpenAI-compatible custom endpoint."""

    normalized_name = (provider_name or "openai").strip().lower()
    return DEFAULT_LLM_MODELS.get(normalized_name, DEFAULT_OPENAI_MODEL)
