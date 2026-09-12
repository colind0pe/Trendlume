import asyncio
import base64
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from src.providers.publishing.browser import BrowserManager


@dataclass
class QRSessionState:
    """Active interactive QR Code Login Session"""

    session_id: str
    platform: str
    status: str = "initializing"  # initializing, pending, success, expired, timeout, error
    qrcode_data_url: str | None = None
    storage_state: dict[str, Any] | None = None
    error_message: str | None = None
    user_info: dict[str, Any] = field(default_factory=dict)


async def _locator_to_data_url(locator: Any) -> str:
    """Extract src or take screenshot of locator as Base64 Data URL."""
    try:
        src = await locator.get_attribute("src")
        if src and src.startswith("data:image"):
            return src
    except Exception:
        pass
    screenshot_bytes = await locator.screenshot()
    return f"data:image/png;base64,{base64.b64encode(screenshot_bytes).decode('utf-8')}"


class PlatformAuthService:
    """Manages interactive login sessions for social platforms (Douyin, Mock)."""

    def __init__(self):
        self._sessions: dict[str, QRSessionState] = {}
        self._cancel_callbacks: dict[str, Callable[[], None]] = {}

    def start_qr_session(self, platform: str, headless: bool = True) -> QRSessionState:
        """Start an async interactive QR login session for the given platform.

        Runs in a dedicated background thread with ProactorEventLoop on Windows.
        """
        platform_clean = platform.lower().strip()
        session_id = f"qr_{platform_clean}_{uuid.uuid4().hex[:8]}"

        session = QRSessionState(
            session_id=session_id,
            platform=platform_clean,
            status="initializing",
        )
        self._sessions[session_id] = session

        def _run_in_thread():
            if sys.platform == "win32":
                new_loop = asyncio.ProactorEventLoop()
            else:
                new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            task = new_loop.create_task(
                self._run_login_flow(session, headless=headless)
            )
            self._cancel_callbacks[session_id] = lambda: new_loop.call_soon_threadsafe(
                task.cancel
            )
            try:
                new_loop.run_until_complete(task)
            except Exception as ex:
                logger.error(f"Error in background login thread for {session_id}: {ex}")
            finally:
                self._cancel_callbacks.pop(session_id, None)
                try:
                    new_loop.close()
                except Exception:
                    pass

        t = threading.Thread(target=_run_in_thread, daemon=True, name=f"QRAuth_{session_id}")
        t.start()

        logger.info(f"Started QR login session {session_id} for {platform_clean}")
        return session

    def get_qr_session(self, session_id: str) -> QRSessionState | None:
        """Get state of an active or recent QR login session"""
        return self._sessions.get(session_id)

    def cancel_qr_session(self, session_id: str) -> bool:
        """Cancel an ongoing QR login session"""
        session = self._sessions.get(session_id)
        if not session or session.status in {"success", "expired", "timeout", "error"}:
            return False
        session.status = "error"
        session.error_message = "已取消扫码登录会话"
        cancel = self._cancel_callbacks.get(session_id)
        if cancel:
            try:
                cancel()
            except RuntimeError:
                pass
        return True

    async def _run_login_flow(self, session: QRSessionState, headless: bool = True):
        """Dispatches login flow to platform-specific worker"""
        try:
            if session.status == "error":
                return
            if session.platform == "douyin":
                await self._douyin_qr_flow(session, headless=headless)
            elif session.platform == "mock":
                await self._mock_qr_flow(session)
            else:
                session.status = "error"
                session.error_message = f"暂不支持平台的扫码登录: {session.platform}"
        except asyncio.CancelledError:
            session.status = "error"
            session.error_message = "扫码登录已取消"
        except Exception as e:
            logger.error(f"Error in QR login session {session.session_id}: {e}")
            session.status = "error"
            session.error_message = str(e)

    async def _poll_for_login(
        self, session: QRSessionState, b_session: Any, check_func: Any, timeout_msg: str
    ):
        """Generic polling loop for QR login status"""
        max_seconds = 180
        poll_interval = 2
        elapsed = 0

        while elapsed < max_seconds:
            if session.status == "error":
                break

            try:
                is_logged_in = await check_func()
                if is_logged_in:
                    # Give the browser session time to complete asynchronous token exchanges and persist cookies
                    await asyncio.sleep(1.5)
                    if session.status == "error":
                        return
                    session.storage_state = await b_session.get_storage_state()
                    if session.status == "error":
                        return
                    session.status = "success"
                    logger.info(
                        f"{session.platform} login succeeded for session {session.session_id}"
                    )
                    return
            except Exception as e:
                logger.debug(f"Error during {session.platform} login check: {e}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if session.status not in {"success", "error"}:
            session.status = "timeout"
            session.error_message = timeout_msg

    # ========================================================================
    # Platform QR Login Flows
    # ========================================================================

    async def _douyin_qr_flow(self, session: QRSessionState, headless: bool = True):
        """Handles Douyin creator center QR code capture and login polling."""
        async with BrowserManager.get_session(
            platform="douyin", headless=headless, timeout_ms=120000
        ) as b_session:
            page = b_session.page
            await page.goto(
                "https://creator.douyin.com/", wait_until="domcontentloaded", timeout=60000
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            scan_login_tab = page.get_by_text("扫码登录", exact=True).first
            try:
                await scan_login_tab.wait_for(state="attached", timeout=60000)
            except Exception:
                pass

            qrcode_selectors = [
                'div#animate_qrcode_container img[src^="data:image"]',
                'div[class*="animate_qrcode_container"] img[src^="data:image"]',
                'div[class*="scan_qrcode_login_content"] img[src^="data:image"]',
                'div[class*="qrcode"] img[src^="data:image"]',
                'img[aria-label="二维码"]',
                "div#animate_qrcode_container canvas",
                'div[class*="animate_qrcode_container"] canvas',
                'div[class*="scan_qrcode_login_content"] canvas',
                "canvas",
            ]

            async def extract_qr() -> str | None:
                for sel in qrcode_selectors:
                    loc = page.locator(sel).first
                    try:
                        await loc.wait_for(state="attached", timeout=4000)
                        if await loc.count():
                            src = await loc.get_attribute("src")
                            if src and src.startswith("data:image/"):
                                return src
                            # Fallback if canvas/screenshot needed
                            return await _locator_to_data_url(loc)
                    except Exception:
                        continue
                return None

            qr_data = await extract_qr()
            if not qr_data:
                fb = page.locator(
                    'div[class*="login"] img, div[class*="qrcode"] img, canvas'
                ).first
                if await fb.count():
                    await fb.wait_for(state="visible", timeout=10000)
                    qr_data = await _locator_to_data_url(fb)

            if session.status == "error":
                return
            session.qrcode_data_url = qr_data
            session.status = "pending"
            logger.info(f"Douyin QR code acquired for session {session.session_id}")

            async def check_login():
                # 1. Check if URL navigated to creator micro management/dashboard
                if "creator.douyin.com/creator-micro" in page.url:
                    # Check if actual login dialog or QR code is still visible
                    login_markers = [
                        page.locator('div#animate_qrcode_container').first,
                        page.locator('div[class*="scan_qrcode_login_content"]').first,
                        page.locator('div[class*="login-container"]').first,
                        page.get_by_text("二维码失效", exact=True).first,
                    ]
                    has_visible_marker = False
                    for marker in login_markers:
                        if await marker.count():
                            try:
                                if await marker.is_visible():
                                    has_visible_marker = True
                                    break
                            except Exception:
                                pass
                    if not has_visible_marker:
                        # Try to capture username & display name
                        try:
                            name_el = page.locator(
                                ".name-text, .user-name, [class*='avatar-name'], [class*='userName'], [class*='user-card']"
                            ).first
                            if await name_el.count():
                                u_name = (await name_el.inner_text()).strip()
                                if u_name:
                                    session.user_info["username"] = u_name
                                    session.user_info["display_name"] = u_name
                        except Exception:
                            pass
                        await page.wait_for_timeout(2000)
                        return True

                # 2. Check context cookies for active session cookies
                try:
                    cookies = await b_session.context.cookies()
                    has_session = any(
                        c.get("name") in ["sessionid", "sessionid_ss", "sid_tt", "passport_auth_status"]
                        and c.get("value")
                        for c in cookies
                    )
                    if has_session and "creator.douyin.com" in page.url:
                        qr_box = page.locator(
                            'div#animate_qrcode_container img, div[class*="scan_qrcode_login_content"] img'
                        ).first
                        if not (await qr_box.count() and await qr_box.is_visible()):
                            await page.wait_for_timeout(2000)
                            return True
                except Exception:
                    pass

                expired_box = page.get_by_text("二维码失效", exact=True).first
                if await expired_box.count() and await expired_box.is_visible():
                    await expired_box.click()
                    await page.wait_for_timeout(1500)
                    new_qr = await extract_qr()
                    if new_qr:
                        session.qrcode_data_url = new_qr
                return False

            await self._poll_for_login(session, b_session, check_login, "抖音扫码登录超时，请重新获取二维码")

    async def _mock_qr_flow(self, session: QRSessionState):
        """Simulates QR generation and fast automatic login for tests"""
        session.qrcode_data_url = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        session.status = "pending"
        await asyncio.sleep(0.5)
        if session.status == "error":
            return
        session.storage_state = {
            "cookies": [
                {
                    "name": "sessionid",
                    "value": "mock_session_123456",
                    "domain": ".douyin.com",
                    "path": "/",
                }
            ],
            "origins": [],
        }
        session.status = "success"
        session.user_info = {"username": "douyin_creator", "display_name": "抖音创作者Pro"}


# Global singleton
auth_service = PlatformAuthService()
