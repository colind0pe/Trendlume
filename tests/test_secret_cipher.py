import pytest

from src.core.security import SecretCipher


def test_secret_cipher_encrypts_and_rejects_wrong_key():
    cipher = SecretCipher("custom-test-key-12345")
    secret = "sk-deepseek-1234567890abcdef"
    encrypted = cipher.encrypt(secret)
    assert encrypted != secret
    assert cipher.decrypt(encrypted) == secret

    wrong_cipher = SecretCipher("different-test-key-67890")
    with pytest.raises(ValueError, match="Invalid encryption key"):
        wrong_cipher.decrypt(encrypted)
    assert wrong_cipher.decrypt_dict(encrypted) == {}


def test_secret_cipher_dict_encryption():
    cipher = SecretCipher()
    data = {
        "api_key": "sk-test-key-abc",
        "client_secret": "my-secret-token",
        "nested_empty": None,
    }
    encrypted = cipher.encrypt_dict(data)
    assert encrypted is not None
    assert "sk-test-key-abc" not in encrypted

    decrypted = cipher.decrypt_dict(encrypted)
    assert decrypted["api_key"] == "sk-test-key-abc"
    assert decrypted["client_secret"] == "my-secret-token"
    assert "nested_empty" not in decrypted
    assert cipher.encrypt_dict({"nested_empty": None}) is None
    assert cipher.decrypt_dict(None) == {}


def test_secret_cipher_masking():
    assert SecretCipher.mask_secret("") == ""
    assert SecretCipher.mask_secret("1234") == "••••••••"
    masked = SecretCipher.mask_secret("sk-1234567890abcdef")
    assert "••••••••" in masked
    assert not masked.startswith("sk-1234567890abcdef")

    assert SecretCipher.is_masked("sk-ab••••••••ef") is True
    assert SecretCipher.is_masked("••••••••") is True
    assert SecretCipher.is_masked("sk-actualplaintextkey") is False
