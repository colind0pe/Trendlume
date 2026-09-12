import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.providers.publishing.cookie_helper import normalize_storage_state

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
(() => {
    // Overwrite navigator.webdriver to hide automation flags
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // Mock chrome object
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            loadTimes: () => {},
            csi: () => {},
            app: {},
        };
    }

    // Mock languages and plugins
    Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en'],
    });

    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
})();
"""


class BrowserSession:
    """Encapsulates active Playwright session objects for clean usage."""

    def __init__(self, browser: Browser, context: BrowserContext, page: Page):
        self.browser = browser
        self.context = context
        self.page = page

    async def get_storage_state(self) -> dict[str, Any]:
        """Extract current storage_state (cookies + localStorage) from context."""
        return await self.context.storage_state()


class BrowserManager:
    """Playwright Browser Context Manager with stealth protection, channel fallbacks,

    and automated cleanup.
    """

    @classmethod
    async def _launch_browser(cls, playwright: Any, headless: bool, args: list[str]) -> Browser:
        """Attempt launching default chromium, then fallback to system installed chrome or msedge."""
        # 1. Try standard chromium
        try:
            return await playwright.chromium.launch(headless=headless, args=args)
        except Exception as e:
            logger.debug(f"Default Playwright chromium launch failed: {e}. Trying system channels...")

        # 2. Try system channels (chrome, msedge)
        for channel in ["chrome", "msedge"]:
            try:
                browser = await playwright.chromium.launch(
                    channel=channel,
                    headless=headless,
                    args=args,
                )
                logger.info(f"Successfully launched browser using channel: {channel}")
                return browser
            except Exception as ch_err:
                logger.debug(f"Channel {channel} failed: {ch_err}")

        raise RuntimeError("无法启动 Chromium 浏览器，请确保本地已安装 Google Chrome 或 Microsoft Edge 浏览器。")

    @classmethod
    @asynccontextmanager
    async def get_session(
        cls,
        credential_data: Any | None = None,
        platform: str = "",
        headless: bool = True,
        user_agent: str | None = None,
        timeout_ms: int = 60000,
    ) -> AsyncGenerator[BrowserSession, None]:
        """Async context manager providing an anti-detection BrowserSession.

        Guarantees browser and context closure upon exit.
        """
        normalized_state = (
            normalize_storage_state(credential_data, platform=platform)
            if credential_data
            else None
        )

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--lang=zh-CN",
        ]

        playwright = await async_playwright().start()
        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            browser = await cls._launch_browser(playwright, headless=headless, args=launch_args)

            context_kwargs: dict[str, Any] = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": user_agent or DEFAULT_USER_AGENT,
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
            }

            if normalized_state and (
                normalized_state.get("cookies") or normalized_state.get("origins")
            ):
                context_kwargs["storage_state"] = normalized_state

            context = await browser.new_context(**context_kwargs)
            await context.add_init_script(STEALTH_INIT_SCRIPT)
            context.set_default_timeout(timeout_ms)

            page = await context.new_page()
            session = BrowserSession(browser=browser, context=context, page=page)
            yield session

        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.debug(f"Error closing page: {e}")
            if context:
                try:
                    await context.close()
                except Exception as e:
                    logger.debug(f"Error closing browser context: {e}")
            if browser:
                try:
                    await browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")
            try:
                await playwright.stop()
            except Exception as e:
                logger.debug(f"Error stopping playwright: {e}")


async def run_in_proactor_loop(coro_fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run an async coroutine on a dedicated Windows ProactorEventLoop in a separate thread.

    This completely resolves the 'NotImplementedError' when Playwright runs under
    _WindowsSelectorEventLoop in Uvicorn on Windows.
    """
    import sys
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if sys.platform == "win32" and current_loop and "Selector" in type(current_loop).__name__:
        def worker():
            proactor_loop = asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
            asyncio.set_event_loop(proactor_loop)
            try:
                return proactor_loop.run_until_complete(coro_fn(*args, **kwargs))
            finally:
                proactor_loop.close()

        return await asyncio.to_thread(worker)
    else:
        return await coro_fn(*args, **kwargs)
