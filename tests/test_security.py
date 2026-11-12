from __future__ import annotations

from backend.app.security import (
    decrypt_secret,
    encrypt_secret,
    hash_password,
    new_token,
    token_hash,
    verify_password,
    verify_signed_token,
    create_signed_token,
)


def test_password_hash_roundtrip():
    hashed = hash_password("Testpass123")
    assert hashed != "Testpass123"
    assert verify_password("Testpass123", hashed)
    assert not verify_password("wrong-password", hashed)
    assert not verify_password("Testpass123", "not-a-hash")


def test_token_hash_is_deterministic():
    token = new_token()
    assert token not in token_hash(token)
    assert token_hash(token) == token_hash(token)


def test_secret_encryption_roundtrip():
    encrypted = encrypt_secret("session-state-json")
    assert encrypted != "session-state-json"
    assert decrypt_secret(encrypted) == "session-state-json"


def test_signed_tokens_reject_tampering_and_purpose_confusion():
    token = create_signed_token("video-id|user-id", 60, "file")
    assert verify_signed_token(token, "file") == "video-id|user-id"
    assert verify_signed_token(token, "asset") is None
    parts = token.split(".")
    tampered = ".".join(parts[:-1] + ["AAAA"])
    assert verify_signed_token(tampered, "file") is None
    expired = create_signed_token("subject", -1, "file")
    assert verify_signed_token(expired, "file") is None
