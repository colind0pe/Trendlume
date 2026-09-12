from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base
from src.core.security import secret_cipher


class ProviderConfigModel(Base):
    """SQLAlchemy ORM model for unified AI and Service Provider configurations"""

    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Provider category: "llm" | "search" | "image" | "video" | "tts" | "publishing"
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Implementation identifier: "deepseek" | "openai" | "claude" | "cloudflare" | "ollama" | "tavily" | "comfyui" | "edge_tts" | "douyin" | "custom"
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Human-readable display name (e.g. "DeepSeek 官方 API", "本地 ComfyUI 服务")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Enable / Disable flag
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Primary / Default provider for this provider_type
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # Non-sensitive runtime options (base_url, model, workflow, voice, timeout, etc.)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Encrypted credentials payload (Fernet ciphertext containing API keys, OAuth tokens, cookies, etc.)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Persisted result of the most recent explicit connectivity test. These fields
    # contain only safe diagnostics; credentials are never stored here.
    last_test_connected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_test_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    @property
    def masked_credentials(self) -> dict[str, str]:
        """Return credentials dictionary with masked secrets for safe presentation"""
        if not self.credentials_encrypted:
            return {}
        decrypted = secret_cipher.decrypt_dict(self.credentials_encrypted)
        return secret_cipher.mask_dict(decrypted)

    @property
    def has_credentials(self) -> bool:
        """Check if provider has configured credentials"""
        return bool(self.credentials_encrypted and str(self.credentials_encrypted).strip())
