import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger


def retry_async(
    max_retries: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    retry_log_level: str = "warning",
    error_formatter: Callable[[Exception], str] | None = None,
):
    """Decorator to retry async functions with exponential backoff"""

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay_seconds
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    try:
                        error_summary = error_formatter(e) if error_formatter else str(e)
                    except Exception:
                        error_summary = type(e).__name__
                    if attempt == max_retries:
                        logger.error(
                            f"Provider call {func.__name__} failed after {max_retries} attempts: {error_summary}"
                        )
                        raise
                    log_method = getattr(logger, retry_log_level.lower(), None) or logger.warning
                    log_method(
                        f"Provider call {func.__name__} failed (attempt {attempt}/{max_retries}), retrying in {current_delay:.1f}s... Error: {error_summary}"
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor
            raise last_exception  # type: ignore

        return wrapper

    return decorator


def mask_secret(secret: str | None) -> str:
    """Mask secret key for safe logging (e.g. sk-1234****abcd)"""
    if not secret or len(secret) < 8:
        return "******" if secret else "None"
    return f"{secret[:4]}****{secret[-4:]}"
