from __future__ import annotations

import logging
from typing import Any

UVICORN_ACCESS_LOGGER = "uvicorn.access"


def _status_code_from_record(record: logging.LogRecord) -> int | None:
    args: Any = record.args
    if not isinstance(args, tuple) or not args:
        return None
    status_code = args[-1]
    if isinstance(status_code, bool):
        return None
    if isinstance(status_code, int):
        return status_code
    if isinstance(status_code, str) and status_code.isdigit():
        return int(status_code)
    return None


class SuppressSuccessfulAccessLog(logging.Filter):
    """Hide noisy successful Uvicorn access lines while keeping diagnostics."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != UVICORN_ACCESS_LOGGER:
            return True
        status_code = _status_code_from_record(record)
        return status_code is None or not 200 <= status_code < 300


def install_uvicorn_access_log_filter() -> None:
    access_logger = logging.getLogger(UVICORN_ACCESS_LOGGER)
    if not any(isinstance(item, SuppressSuccessfulAccessLog) for item in access_logger.filters):
        access_logger.addFilter(SuppressSuccessfulAccessLog())


class SuppressAsyncioConnLostLog(logging.Filter):
    """Filter out asyncio proactor 'socket.send() raised exception.' warnings
    caused by client disconnecting from HTTP/SSE streaming responses on Windows."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "asyncio":
            message = record.getMessage()
            if "socket.send() raised exception." in message or "socket.sendto() raised exception." in message:
                return False
        return True


def install_asyncio_log_filter() -> None:
    asyncio_logger = logging.getLogger("asyncio")
    if not any(isinstance(item, SuppressAsyncioConnLostLog) for item in asyncio_logger.filters):
        asyncio_logger.addFilter(SuppressAsyncioConnLostLog())


def install_log_filters() -> None:
    install_uvicorn_access_log_filter()
    install_asyncio_log_filter()
