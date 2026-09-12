from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class StructuredOutputException(Exception):
    """LLM output could not be parsed or validated against the requested schema."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    # OpenAI-compatible endpoints are opt-in because compatibility alone does
    # not prove support for response_format=json_schema.
    supports_native_json_schema: bool

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: dict | None = None,
    ) -> str:
        """Generate free-form text from prompt"""
        ...

    async def generate_structured(
        self,
        prompt: str,
        schema_class: type[T],
        system_prompt: str | None = None,
        temperature: float = 0.5,
        **kwargs,
    ) -> T:
        """Generate structured data adhering to a Pydantic schema"""
        ...
