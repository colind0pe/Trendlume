"""Shared Playwright renderer for template previews and production frames."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger

from src.core.exceptions import ValidationException
from src.services.template_catalog import render_template_html, template_catalog

T = TypeVar("T")


class _PersistentProactorWorker:
    """Own a long-lived Windows Proactor loop for async Playwright objects."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready: threading.Event | None = None
        self._startup_error: BaseException | None = None
        self._accepting = True
        self._pending: set[Future[Any]] = set()

    def is_active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    async def submit(self, coroutine_factory: Callable[[], Awaitable[T]]) -> T:
        loop = await asyncio.to_thread(self._ensure_started)
        coroutine = coroutine_factory()
        with self._lock:
            if not self._accepting or self._loop is not loop:
                coroutine.close()
                raise RuntimeError("Playwright worker is closing")
            try:
                future = asyncio.run_coroutine_threadsafe(coroutine, loop)
            except BaseException:
                coroutine.close()
                raise
            self._pending.add(future)
        future.add_done_callback(self._discard_pending)
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.cancel()
            raise

    async def close(self, coroutine_factory: Callable[[], Awaitable[None]]) -> None:
        with self._lock:
            thread = self._thread
            ready = self._ready
            if thread is None:
                self._accepting = True
                return
            self._accepting = False

        if ready is not None:
            await asyncio.to_thread(ready.wait)

        with self._lock:
            loop = self._loop
            startup_error = self._startup_error
            pending = list(self._pending)

        if pending:
            await asyncio.gather(
                *(asyncio.wrap_future(future) for future in pending),
                return_exceptions=True,
            )

        if loop is not None and thread.is_alive() and startup_error is None:
            coroutine = coroutine_factory()
            try:
                close_future = asyncio.run_coroutine_threadsafe(coroutine, loop)
                await asyncio.wrap_future(close_future)
            except BaseException:
                coroutine.close()
            finally:
                loop.call_soon_threadsafe(loop.call_later, 0, loop.stop)

        await asyncio.to_thread(thread.join)
        with self._lock:
            if self._thread is thread:
                self._thread = None
                self._loop = None
                self._ready = None
                self._startup_error = None
                self._pending.clear()
                self._accepting = True

    def _ensure_started(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            thread = self._thread
            ready = self._ready
            if thread is None or not thread.is_alive():
                self._startup_error = None
                self._accepting = True
                ready = threading.Event()
                self._ready = ready
                thread = threading.Thread(
                    target=self._thread_main,
                    args=(ready,),
                    name="trendlume-playwright",
                    daemon=True,
                )
                self._thread = thread
                thread.start()

        if ready is None:  # pragma: no cover - guarded by the initialization above
            raise RuntimeError("Playwright worker failed to initialize")
        ready.wait()
        with self._lock:
            if self._startup_error is not None:
                error = self._startup_error
            elif self._loop is None:
                error = RuntimeError("Playwright worker loop is unavailable")
            else:
                return self._loop
        raise RuntimeError("Playwright worker failed to start") from error

    def _thread_main(self, ready: threading.Event) -> None:
        loop: asyncio.AbstractEventLoop | None = None
        try:
            if sys.platform != "win32":
                raise RuntimeError("The Proactor worker is only available on Windows")
            loop = asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
            asyncio.set_event_loop(loop)
            with self._lock:
                self._loop = loop
        except BaseException as exc:  # pragma: no cover - depends on host runtime
            with self._lock:
                self._startup_error = exc
            ready.set()
            return

        ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            asyncio.set_event_loop(None)
            loop.close()
            with self._lock:
                if self._loop is loop:
                    self._loop = None

    def _discard_pending(self, future: Future[Any]) -> None:
        with self._lock:
            self._pending.discard(future)


class TemplateRenderer:
    _playwright = None
    _browser = None
    _loop: asyncio.AbstractEventLoop | None = None
    _worker = _PersistentProactorWorker()
    _worker_playwright = None
    _worker_browser = None
    _worker_init_lock: asyncio.Lock | None = None

    @classmethod
    async def check_available(cls) -> bool:
        """Start Chromium once as a deployment health check."""
        try:
            if cls._requires_proactor_worker():
                await cls._worker.submit(cls._check_available_on_worker)
            else:
                await cls._ensure_browser()
            return True
        except ValidationException:
            return False
        except Exception:
            logger.exception("Playwright worker health check failed")
            return False

    @staticmethod
    def _requires_proactor_worker() -> bool:
        if sys.platform != "win32":
            return False
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return isinstance(current_loop, asyncio.SelectorEventLoop)

    @classmethod
    async def _ensure_browser(cls):
        current_loop = asyncio.get_running_loop()
        if cls._browser is not None and cls._loop is current_loop and cls._browser.is_connected():
            return cls._browser
        await cls._close_current_loop_browser()
        try:
            from playwright.async_api import async_playwright

            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            cls._loop = current_loop
            return cls._browser
        except Exception as exc:  # pragma: no cover - depends on host installation
            await cls._close_current_loop_browser()
            raise ValidationException(
                "模板渲染需要可用的 Playwright Chromium，请执行 playwright install chromium。"
            ) from exc

    @classmethod
    async def _check_available_on_worker(cls) -> bool:
        await cls._ensure_browser_on_worker()
        return True

    @classmethod
    async def _ensure_browser_on_worker(cls):
        if cls._worker_browser is not None and cls._worker_browser.is_connected():
            return cls._worker_browser

        if cls._worker_init_lock is None:
            cls._worker_init_lock = asyncio.Lock()
        async with cls._worker_init_lock:
            if cls._worker_browser is not None and cls._worker_browser.is_connected():
                return cls._worker_browser
            await cls._close_worker_browser()
            try:
                from playwright.async_api import async_playwright

                cls._worker_playwright = await async_playwright().start()
                cls._worker_browser = await cls._worker_playwright.chromium.launch(
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                return cls._worker_browser
            except Exception as exc:  # pragma: no cover - depends on host installation
                await cls._close_worker_browser()
                raise ValidationException(
                    "模板渲染需要可用的 Playwright Chromium，请执行 playwright install chromium。"
                ) from exc

    @classmethod
    async def _close_current_loop_browser(cls) -> None:
        if cls._browser is not None:
            try:
                await cls._browser.close()
            except Exception:
                pass
        if cls._playwright is not None:
            try:
                await cls._playwright.stop()
            except Exception:
                pass
        cls._browser = None
        cls._playwright = None
        cls._loop = None

    @classmethod
    async def _close_worker_browser(cls) -> None:
        if cls._worker_browser is not None:
            try:
                await cls._worker_browser.close()
            except Exception:
                pass
        if cls._worker_playwright is not None:
            try:
                await cls._worker_playwright.stop()
            except Exception:
                pass
        cls._worker_browser = None
        cls._worker_playwright = None
        cls._worker_init_lock = None

    @classmethod
    async def close(cls) -> None:
        if cls._worker.is_active():
            await cls._worker.close(cls._close_worker_browser)
        await cls._close_current_loop_browser()

    @staticmethod
    async def _capture_page(
        browser: Any,
        *,
        width: int,
        height: int,
        html_path: Path,
        destination: Path,
        transparent: bool,
    ) -> None:
        page = None
        try:
            page = await browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            await page.screenshot(path=str(destination), type="png", omit_background=transparent)
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    logger.debug("Failed to close Playwright page after rendering")

    @classmethod
    async def _render_on_worker(
        cls,
        *,
        width: int,
        height: int,
        html_path: Path,
        destination: Path,
        transparent: bool,
    ) -> None:
        browser = await cls._ensure_browser_on_worker()
        await cls._capture_page(
            browser,
            width=width,
            height=height,
            html_path=html_path,
            destination=destination,
            transparent=transparent,
        )

    @staticmethod
    def _file_uri(path: str | Path | None) -> str:
        if not path:
            return ""
        candidate = Path(path)
        if candidate.exists():
            return candidate.resolve().as_uri()
        return str(path)

    @staticmethod
    def _validate_css(custom_css: str | None) -> str:
        css = custom_css or ""
        if re.search(
            r"@import|url\s*\(|expression\s*\(|javascript:|</?style|</?script|<iframe",
            css,
            re.I,
        ):
            raise ValidationException("自定义 CSS 不允许导入外部资源或执行代码。")
        return css

    @staticmethod
    def _strip_external_resources(html: str) -> str:
        """Keep bundled templates offline and deterministic.

        The Demo markup contains Google Fonts links and a few historical remote
        background URLs.  Chromium is intentionally run with a restrictive CSP,
        but removing those tags/URLs before navigation also prevents network
        waits and makes the same HTML safe for preview and production rendering.
        """
        html = re.sub(
            r"<link\b[^>]*(?:href|src)\s*=\s*['\"]https?://[^'\"]+['\"][^>]*>\s*",
            "",
            html,
            flags=re.IGNORECASE,
        )
        html = re.sub(
            r"<script\b[^>]*(?:src|href)\s*=\s*['\"]https?://[^'\"]+['\"][^>]*>.*?</script>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        html = re.sub(
            r"url\(\s*(['\"]?)https?://[^)'\"]+\1\s*\)",
            "none",
            html,
            flags=re.IGNORECASE,
        )
        return html

    @classmethod
    async def render(
        cls,
        template_id: str | None,
        *,
        title: str = "Trendlume",
        text: str = "AI 短视频模板预览",
        image_path: str | Path | None = None,
        custom_params: dict | None = None,
        custom_css: str | None = None,
        transparent: bool = False,
        output_path: str | Path | None = None,
    ) -> Path:
        item = template_catalog.get(template_id)
        if not item:
            raise ValidationException(f"模板不存在: {template_id}")
        source = template_catalog.resolve_path(item["id"])
        template = source.read_text(encoding="utf-8")

        values = {
            "title": title or "",
            "text": text or "",
            "narration": text or "",
            "author": "",
            "describe": "",
            "description": "",
            "brand": "",
            # ``subtitle`` is an optional template parameter.  Do not map it
            # to the narration by default: templates such as ``image_book``
            # intentionally use a subtitle default (for example, ``作者``),
            # and populating it here renders the same narration twice.
            "index": 1,
            "image": cls._file_uri(image_path),
        }
        values.update(custom_params or {})
        rendered = render_template_html(template, values)
        rendered = cls._strip_external_resources(rendered)
        css = cls._validate_css(custom_css)
        if css:
            rendered = rendered.replace("</head>", f"<style>{css}</style></head>", 1)
        if transparent:
            transparent_css = (
                '<style id="trendlume-transparent-override">'
                "html, body {"
                "  background: transparent !important;"
                "  background-color: transparent !important;"
                "}"
                ".video-overlay, "
                ".background-image, "
                ".glass-base-overlay, "
                ".aurora-background, "
                ".warm-background, "
                ".ambient-glow-layer, "
                ".page-container, "
                ".main-container {"
                "  background: transparent !important;"
                "  background-image: none !important;"
                "  box-shadow: none !important;"
                "}"
                "</style>"
            )
            rendered = rendered.replace("</head>", f"{transparent_css}</head>", 1)
        # Block external navigation/resources from bundled templates while
        # allowing their inline layout scripts to run.
        csp = (
            '<meta http-equiv="Content-Security-Policy" '
            "content=\"default-src 'none'; img-src file: data:; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; font-src file: data:\">"
        )
        rendered = rendered.replace("<head>", f"<head>{csp}", 1)

        destination = Path(output_path) if output_path else Path(tempfile.mkstemp(suffix=".png")[1])
        destination.parent.mkdir(parents=True, exist_ok=True)
        html_path: Path | None = None
        try:
            fd, html_name = tempfile.mkstemp(suffix=".html", prefix="trendlume-template-")
            os.close(fd)
            Path(html_name).write_text(rendered, encoding="utf-8")
            Path(html_name).chmod(0o600)
            html_path = Path(html_name)
            if cls._requires_proactor_worker():
                await cls._worker.submit(
                    lambda: cls._render_on_worker(
                        width=item["width"],
                        height=item["height"],
                        html_path=html_path,
                        destination=destination,
                        transparent=transparent,
                    )
                )
            else:
                browser = await cls._ensure_browser()
                await cls._capture_page(
                    browser,
                    width=item["width"],
                    height=item["height"],
                    html_path=html_path,
                    destination=destination,
                    transparent=transparent,
                )
            if not destination.exists() or destination.stat().st_size == 0:
                raise ValidationException("模板渲染未生成有效预览图。")
            return destination
        except ValidationException:
            raise
        except Exception as exc:
            logger.exception("Template rendering failed")
            raise ValidationException(f"模板渲染失败: {type(exc).__name__}") from exc
        finally:
            if html_path and html_path.exists():
                html_path.unlink(missing_ok=True)
            # mkstemp creates an empty file before Playwright writes it; keep
            # the caller-owned output but clean an anonymous temporary file on
            # failure.
