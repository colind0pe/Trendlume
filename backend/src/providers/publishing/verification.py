import asyncio
import threading
import time
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class VerificationRequest:
    """State of an active verification request required by a platform publisher."""

    request_id: str
    job_id: str
    account_id: str
    platform: str
    prompt: str
    account_name: str = ""
    title: str = ""
    status: str = "pending"  # "pending", "submitted", "completed", "expired", "cancelled"
    code: str | None = None
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 120.0
    error_message: str | None = None
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def remaining_seconds(self) -> int:
        """Returns the number of seconds remaining before timeout."""
        elapsed = time.time() - self.created_at
        rem = int(self.timeout_seconds - elapsed)
        return max(0, rem)

    @property
    def is_expired(self) -> bool:
        """Returns True if the request has timed out."""
        return self.remaining_seconds <= 0


class VerificationManager:
    """Thread-safe manager for coordinating interactive verification code submissions

    between background workers and UI / API consumers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[str, VerificationRequest] = {}

    def request_code(
        self,
        job_id: str,
        account_id: str,
        platform: str,
        prompt: str,
        account_name: str = "",
        title: str = "",
        timeout_seconds: float = 120.0,
    ) -> VerificationRequest:
        """Register a new verification request for a publishing job."""
        request_id = f"ver_{platform}_{job_id}"
        with self._lock:
            old_req = self._requests.get(request_id)
            if old_req and old_req.status == "pending":
                old_req.status = "cancelled"
                old_req._event.set()

            req = VerificationRequest(
                request_id=request_id,
                job_id=job_id,
                account_id=account_id,
                account_name=account_name or "",
                title=title or "",
                platform=platform,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
            self._requests[request_id] = req
            logger.info(
                f"Created interactive verification request: {request_id} for job {job_id} on {platform}"
            )
            return req

    def _expire_if_needed(self, req: VerificationRequest) -> bool:
        """Helper to mark request expired if timed out. Must be called under self._lock."""
        if req.status == "pending" and req.is_expired:
            req.status = "expired"
            req.error_message = "验证请求已超时"
            req._event.set()
            return True
        return False

    def list_pending_requests(self) -> list[VerificationRequest]:
        """List all currently active, non-expired verification requests awaiting user input."""
        with self._lock:
            pending = []
            for req in list(self._requests.values()):
                if req.status == "pending":
                    if not self._expire_if_needed(req):
                        pending.append(req)
            return pending

    def submit_code(self, request_id: str, code: str) -> bool:
        """Submit a verification code for an active request from UI or API."""
        clean_code = str(code).strip()
        if not clean_code:
            return False

        with self._lock:
            req = self._requests.get(request_id)
            if not req:
                return False
            if req.status != "pending" or req.is_expired:
                return False
            req.code = clean_code
            req.status = "submitted"
            req._event.set()
            logger.info(f"Verification code submitted for {request_id}")
            return True

    def cancel_request(self, request_id: str) -> bool:
        """Cancel an active verification request."""
        with self._lock:
            req = self._requests.get(request_id)
            if not req:
                return False
            req.status = "cancelled"
            req.error_message = "用户取消了验证"
            req._event.set()
            logger.info(f"Verification request cancelled for {request_id}")
            return True

    def complete_request(self, request_id: str) -> None:
        """Mark a verification request as completed and clean up."""
        with self._lock:
            req = self._requests.get(request_id)
            if req:
                req.status = "completed"
                self._requests.pop(request_id, None)

    async def wait_for_code(self, request_id: str) -> str | None:
        """Asynchronously wait for the user to submit a code for the given request."""
        with self._lock:
            req = self._requests.get(request_id)
            if req:
                self._expire_if_needed(req)
        if not req:
            return None

        start_time = time.time()
        while time.time() - start_time < req.timeout_seconds:
            if req._event.is_set():
                if req.status == "submitted" and req.code:
                    return req.code
                elif req.status in ["cancelled", "expired"]:
                    return None
            await asyncio.sleep(0.5)

        with self._lock:
            if req.status == "pending":
                req.status = "expired"
                req.error_message = "验证码输入超时"
                req._event.set()
        return None


# Global singleton manager
verification_manager = VerificationManager()
