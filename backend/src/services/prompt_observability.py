"""Bounded, secret-free observation of production LLM calls."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

from loguru import logger
from sqlalchemy import text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.exceptions import ProviderException, ValidationException
from src.core.security import redact_sensitive_text
from src.models.prompt_observation import PromptCallObservationModel
from src.providers.llm.protocol import StructuredOutputException
from src.services.prompt_registry import PromptSpec

T = TypeVar("T")
_SIGNED_QUERY = re.compile(
    r"(?i)([?&](?:x-amz-[^=]+|signature|sig|token|key|credential|expires)=)[^&\s]+"
)
_URL = re.compile(r"(?i)https?://[^\s]+")
_SIGNED_LABEL = re.compile(r"(?i)signed[_ -]?url")
_SQLITE_BUSY_RETRY_DELAYS = (0.05, 0.1)
_SQLITE_PERSIST_BUSY_TIMEOUT_MS = 250
_PERSIST_TIMEOUT_SECONDS = 1.0


def _safe_text(value: Any, limit: int = 12000) -> str:
    text = redact_sensitive_text(str(value or ""), limit=limit)
    text = _SIGNED_QUERY.sub(r"\1[REDACTED]", text)
    text = _SIGNED_LABEL.sub("url", text)
    return _URL.sub("[URL_REDACTED]", text)


def _safe_hash(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(_safe_text(value).encode("utf-8")).hexdigest()


def _safe_usage(value: Any) -> dict[str, int | float] | None:
    if not isinstance(value, Mapping):
        return None
    result: dict[str, int | float] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        result[str(key)[:80]] = item
    return result or None


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, ProviderException):
        return "provider"
    if isinstance(exc, StructuredOutputException):
        return "structured_output"
    if isinstance(exc, ValidationException) or isinstance(exc, (ValueError, TypeError)):
        return "validation"
    return "internal"


def _database_error_category(exc: BaseException) -> str | None:
    """Classify SQLAlchemy operational failures without logging their details."""
    if not isinstance(exc, OperationalError):
        return None

    messages: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current).casefold())
        current = current.__cause__ or current.__context__
    text = " ".join(messages)

    if any(
        marker in text
        for marker in ("no such table", "undefined table", "does not exist")
    ):
        return "schema_missing"
    if any(
        marker in text
        for marker in ("database is locked", "database table is locked", "busy")
    ):
        return "sqlite_busy"
    return "database_operational"


class PromptCallContext:
    def __init__(
        self,
        spec: PromptSpec,
        *,
        temperature: float | None,
        max_tokens: int | None,
        mode: str,
        native_json_schema: bool = False,
    ):
        self.spec = spec
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.mode = mode
        self.native_json_schema = native_json_schema
        self.observation_id: str | None = None


class PromptObservationRecorder:
    """Record safe in-memory observations and best-effort durable rows."""

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        task_id: str | None = None,
        job_id: str | None = None,
        step_run_id: str | None = None,
    ):
        self.db = db
        self.task_id = task_id
        self.job_id = job_id
        self.step_run_id = step_run_id
        self.records: list[dict[str, Any]] = []
        self._session_factory = self._build_session_factory(db)
        self._schema_missing_logged = False

    @staticmethod
    def _build_session_factory(db: AsyncSession | None):
        if db is None:
            return None
        try:
            bind = db.bind
            return async_sessionmaker(bind=bind, expire_on_commit=False)
        except Exception:
            return None

    async def observe(
        self,
        provider: Any,
        context: PromptCallContext,
        *,
        prompt: str,
        system_prompt: str | None,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        result: T | None = None
        error: Exception | None = None
        try:
            result = await operation()
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            try:
                completed_at = datetime.now(UTC)
                observation = {
                    "id": str(uuid4()),
                    "task_id": self.task_id,
                    "job_id": self.job_id,
                    "step_run_id": self.step_run_id,
                    "prompt_id": context.spec.prompt_id,
                    "prompt_version": context.spec.version,
                    "template_hash": context.spec.template_hash,
                    "provider": str(
                        getattr(provider, "provider_name", None)
                        or getattr(provider, "name", type(provider).__name__)
                    )[:100],
                    "model": _safe_text(getattr(provider, "model", None), limit=200) or None,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "latency_ms": max(0, round((time.perf_counter() - started) * 1000)),
                    "status": "failure" if error else "success",
                    "failure_category": _failure_category(error) if error else None,
                    "temperature": context.temperature,
                    "max_tokens": context.max_tokens,
                    "mode": context.mode,
                    "native_json_schema": bool(
                        context.native_json_schema
                        or getattr(provider, "last_structured_native_json_schema", False)
                    ),
                    "repair_count": max(
                        0, int(getattr(provider, "last_structured_repair_count", 0) or 0)
                    ),
                    "fallback_count": 0,
                    "input_sha256": _safe_hash(
                        {"prompt": prompt, "system_prompt": system_prompt}
                    ),
                    "input_chars": len(_safe_text(prompt)) + len(_safe_text(system_prompt)),
                    "output_sha256": _safe_hash(result) if result is not None else None,
                    "output_chars": len(_safe_text(result)) if result is not None else None,
                    "token_usage": _safe_usage(getattr(provider, "last_usage", None)),
                    "error_summary": _safe_text(str(error), limit=500) if error else None,
                }
                context.observation_id = observation["id"]
                self.records.append(observation)
                await self._persist(observation)
            except Exception as exc:
                # Serialization and observer failures are never generation
                # failures. Keep the diagnostic itself type-only and safe.
                logger.warning("Prompt observation recording skipped: {}", type(exc).__name__)

    def _log_persistence_failure(self, operation: str, category: str, attempts: int) -> None:
        if category == "schema_missing":
            if self._schema_missing_logged:
                return
            self._schema_missing_logged = True
            logger.error(
                "Prompt observation {} skipped: category=schema_missing; "
                "apply the Alembic migrations before starting Trendlume.",
                operation,
            )
            return
        logger.warning(
            "Prompt observation {} skipped: category={}, attempts={}",
            operation,
            category,
            attempts,
        )

    async def _run_persistence_operation(
        self,
        operation: Callable[[], Awaitable[Any]],
        operation_name: str,
    ) -> bool:
        max_attempts = len(_SQLITE_BUSY_RETRY_DELAYS) + 1
        for attempt in range(1, max_attempts + 1):
            try:
                await asyncio.wait_for(operation(), timeout=_PERSIST_TIMEOUT_SECONDS)
                return True
            except TimeoutError:
                self._log_persistence_failure(operation_name, "timeout", attempt)
                return False
            except OperationalError as exc:
                category = _database_error_category(exc) or "database_operational"
                if category == "sqlite_busy" and attempt < max_attempts:
                    await asyncio.sleep(_SQLITE_BUSY_RETRY_DELAYS[attempt - 1])
                    continue
                self._log_persistence_failure(operation_name, category, attempt)
                return False
            except Exception:
                self._log_persistence_failure(operation_name, "observer_error", attempt)
                return False
        return False

    async def mark_fallback(self, context: PromptCallContext, count: int = 1) -> None:
        if count <= 0:
            return
        matching = next(
            (item for item in reversed(self.records) if item["id"] == context.observation_id),
            None,
        )
        if matching is None:
            return
        matching["fallback_count"] = int(matching.get("fallback_count") or 0) + count
        if not self._session_factory:
            return
        session_factory = self._session_factory

        async def update_fallback() -> None:
            async with session_factory() as session:
                await session.execute(
                    update(PromptCallObservationModel)
                    .where(PromptCallObservationModel.id == matching["id"])
                    .values(fallback_count=matching["fallback_count"])
                )
                await session.commit()

        await self._run_persistence_operation(update_fallback, "fallback update")

    async def _persist(self, data: dict[str, Any]) -> None:
        session_factory = self._session_factory
        if not session_factory:
            return

        async def persist_observation() -> None:
            async with session_factory() as session:
                if getattr(getattr(session.bind, "dialect", None), "name", None) == "sqlite":
                    await session.execute(text(f"PRAGMA busy_timeout = {_SQLITE_PERSIST_BUSY_TIMEOUT_MS}"))
                session.add(PromptCallObservationModel(**data))
                await session.commit()

        # Observability must never turn a successful generation into a failed
        # generation. The session is independent from the business session.
        await self._run_persistence_operation(persist_observation, "persistence")
