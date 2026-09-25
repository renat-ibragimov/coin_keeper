"""Password hashing, JWT access tokens and opaque token generation.

Rules come from docs/auth.md: argon2id for passwords, HS256 for access
tokens, and only sha256 digests of refresh and one-time tokens reach the
database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio.to_thread
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"
TOKEN_BYTES = 32
# Every new password; the floor is `password_min_length` in settings.
PASSWORD_MAX_LENGTH = 256

_dummy_hash: str | None = None


class InvalidTokenError(Exception):
    """Raised when an access token is missing, expired or malformed."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return True


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


async def hash_password_async(password: str) -> str:
    """argon2 is ~50 ms of CPU: off the event loop, so a burst of sign-ins
    doesn't stall every other request on the worker."""
    return await anyio.to_thread.run_sync(hash_password, password)


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    """Off the event loop, and as slow for a missing hash as for a real one:
    an account without a password, or no account at all, must not answer
    faster than a wrong password does (docs/auth.md, "Passwords")."""
    global _dummy_hash
    if password_hash is None:
        if _dummy_hash is None:
            _dummy_hash = await hash_password_async(secrets.token_urlsafe(TOKEN_BYTES))
        await anyio.to_thread.run_sync(verify_password, password, _dummy_hash)
        return False
    return await anyio.to_thread.run_sync(verify_password, password, password_hash)


def generate_token() -> str:
    """A fresh opaque token: refresh tokens and one-time email tokens alike."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def derive_successor_token(token: str) -> str:
    """The refresh token that replaces `token` on rotation.

    Deterministic, so a retried or concurrent refresh with the same token gets
    the same successor instead of a second live one (docs/auth.md,
    "Sessions"). Keyed by a subkey of JWT_SECRET: knowing a token's sha256 from
    the database is not enough to derive its successor.
    """
    key = hmac.new(
        get_settings().jwt_secret.encode("utf-8"), b"refresh-successor-v1", hashlib.sha256
    ).digest()
    digest = hmac.new(key, token.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def hash_token(token: str) -> str:
    """Digest stored in the database; the token itself is never persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: int, *, expires_in: timedelta | None = None) -> str:
    settings = get_settings()
    ttl = expires_in or timedelta(minutes=settings.access_token_ttl_minutes)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """Return the user id carried by a valid access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("typ") != "access":
        raise InvalidTokenError("not an access token")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise InvalidTokenError("malformed subject")
    return int(subject)
