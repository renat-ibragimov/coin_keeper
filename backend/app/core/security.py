"""Password hashing, JWT access tokens and opaque token generation.

Rules come from docs/07-auth.md: argon2id for passwords, HS256 for access
tokens, and only sha256 digests of refresh and one-time tokens reach the
database.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"
TOKEN_BYTES = 32


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


def generate_token() -> str:
    """A fresh opaque token: refresh tokens and one-time email tokens alike."""
    return secrets.token_urlsafe(TOKEN_BYTES)


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
