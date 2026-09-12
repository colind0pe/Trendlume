import base64
import hashlib
import json
import re
import traceback
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from src.core.config import settings


class SecretCipher:
    """Symmetric encryption service for database secrets (API Keys, Tokens, OAuth credentials)

    Uses Fernet (AES-128-CBC + HMAC-SHA256 authenticated symmetric encryption).
    Root key comes from settings. A deterministic fallback is allowed only for
    loopback-bound local development.
    """

    def __init__(self, key: str | None = None):
        self._fernet = self._init_fernet(key or getattr(settings, "encryption_key", None))

    @staticmethod
    def _derive_fernet_key(raw_key: str) -> bytes:
        """Deterministically derive a 32-byte URL-safe base64 key from any string"""
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def _init_fernet(self, raw_key: str | None) -> Fernet:
        if raw_key and str(raw_key).strip():
            k_str = str(raw_key).strip()
            if k_str == "your-secure-random-encryption-key-here":
                raise RuntimeError(
                    "Replace the placeholder CREDENTIAL_ENCRYPTION_KEY/ENCRYPTION_KEY "
                    "before starting Trendlume"
                )
            # Try directly if already valid 32-byte urlsafe base64
            try:
                raw_bytes = k_str.encode("utf-8")
                if len(base64.urlsafe_b64decode(raw_bytes)) == 32:
                    return Fernet(raw_bytes)
            except Exception:
                pass
            derived = self._derive_fernet_key(k_str)
            return Fernet(derived)

        if settings.host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError(
                "CREDENTIAL_ENCRYPTION_KEY or ENCRYPTION_KEY is required when Trendlume "
                "listens on a non-loopback address"
            )

        # Preserve zero-config loopback development without exposing a predictable
        # credential key from a network-accessible deployment.
        local_seed = f"trendlume-local-secret-{settings.base_dir}"
        derived = self._derive_fernet_key(local_seed)
        return Fernet(derived)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string into base64 ciphertext string"""
        if not plaintext:
            return ""
        encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64 ciphertext back to plaintext string"""
        if not ciphertext:
            return ""
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            logger.error("Failed to decrypt secret: invalid encryption key or corrupted data")
            raise ValueError("Invalid encryption key or corrupted credential token")

    def encrypt_dict(self, data: dict[str, Any] | None) -> str | None:
        """Serialize dictionary to JSON and encrypt"""
        if not data:
            return None
        # Clean out any None values before encrypting
        cleaned = {k: v for k, v in data.items() if v is not None}
        if not cleaned:
            return None
        json_str = json.dumps(cleaned, ensure_ascii=False)
        return self.encrypt(json_str)

    def decrypt_dict(self, ciphertext: str | None) -> dict[str, Any]:
        """Decrypt ciphertext and deserialize from JSON back to dictionary"""
        if not ciphertext or not str(ciphertext).strip():
            return {}
        try:
            json_str = self.decrypt(ciphertext.strip())
            return json.loads(json_str) if json_str else {}
        except Exception as e:
            logger.error(f"Error decrypting credentials dict: {e}")
            return {}

    @staticmethod
    def mask_secret(secret: str | None) -> str:
        """Mask a sensitive credential for safe UI display and logging (e.g. sk-ab••••••••ef)"""
        if not secret or not str(secret).strip():
            return ""
        s = str(secret).strip()
        if len(s) <= 8:
            return "••••••••"
        if len(s) <= 16:
            return f"{s[:2]}••••••••{s[-2:]}"
        return f"{s[:4]}••••••••{s[-4:]}"

    @staticmethod
    def mask_dict(credentials: dict[str, Any] | None) -> dict[str, str]:
        """Mask all sensitive values in a credentials dictionary"""
        if not credentials:
            return {}
        return {
            k: SecretCipher.mask_secret(str(v)) if v is not None else ""
            for k, v in credentials.items()
        }

    @staticmethod
    def is_masked(val: str | None) -> bool:
        """Check if a string is a masked placeholder returned from frontend"""
        if not val:
            return False
        return "••••" in val or "•" in val or "****" in val


def redact_sensitive_text(value: str | None, limit: int = 1000) -> str:
    """Remove common credential/header patterns before writing diagnostics."""
    if not value:
        return ""
    redacted = str(value)
    # Redact bearer credentials even when they are not attached to a JSON/header key.
    redacted = re.sub(r"(?i)\bBearer\s+[^\s,;\"'}]+", "Bearer [REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)(cookie|token|authorization|api[_-]?key|secret)\s*[\"']?\s*[:=]\s*[\"']?(?:Bearer\s+)?[^\s,;\"'}]+",
        r"\1=[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)([?&](?:x-amz-signature|signature|sig|token|key|credential)=)[^&\s]+",
        r"\1[REDACTED]",
        redacted,
    )
    return redacted[:limit]


def log_exception_safely(log, message: str, exception: BaseException) -> None:
    """Log a traceback without exposing Loguru's local-variable diagnostics."""
    try:
        # Newer logging adapters may support per-call diagnose control.
        log.opt(exception=exception, diagnose=False).error(message)
    except TypeError as opt_error:
        # Loguru 0.7.x exposes ``diagnose`` on handlers, not ``logger.opt``.
        if "diagnose" not in str(opt_error):
            raise
        traceback_info = traceback.TracebackException.from_exception(
            exception, capture_locals=False
        )
        safe_traceback = redact_sensitive_text(
            "".join(traceback_info.format()), limit=10000
        ).rstrip()
        log.error(f"{message}\n{safe_traceback}")


# Global default cipher instance
secret_cipher = SecretCipher()
