from src.core.security import redact_sensitive_text


def test_sensitive_text_is_redacted_before_logging():
    raw = (
        "Authorization: Bearer bearer-secret cookie=session-cookie "
        "token=token-secret https://cdn.test/?X-Amz-Signature=signed-secret"
    )

    redacted = redact_sensitive_text(raw)

    assert all(secret not in redacted for secret in ("bearer-secret", "session-cookie"))
    assert "token-secret" not in redacted
    assert "signed-secret" not in redacted
    assert "[REDACTED]" in redacted
