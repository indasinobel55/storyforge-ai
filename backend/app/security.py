from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import bcrypt
from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def new_token(nbytes: int = 32) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    return Fernet(settings.fernet_key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt provider session") from exc


def _sign(payload: str) -> str:
    signature = hmac.new(settings.secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def create_signed_token(subject: str, ttl_seconds: int, purpose: str) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{purpose}.{subject}.{expires}"
    return f"{payload}.{_sign(payload)}"


def verify_signed_token(token: str, purpose: str) -> str | None:
    try:
        token_purpose, subject, expires, signature = token.rsplit(".", 3) if token.count(".") >= 3 else (None,) * 4
    except ValueError:
        return None
    if not token_purpose or token_purpose != purpose:
        return None
    payload = f"{token_purpose}.{subject}.{expires}"
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        if int(expires) < int(time.time()):
            return None
    except ValueError:
        return None
    return subject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RateLimiter:
    """Small in-process sliding-window limiter.

    This protects single-instance deployments. Multi-instance deployments should
    put a Redis-backed limiter in front of auth and generation endpoints.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = max(1, int(self.window - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, 0


auth_limiter = RateLimiter(limit=12, window_seconds=300)
generation_limiter = RateLimiter(limit=30, window_seconds=3600)
