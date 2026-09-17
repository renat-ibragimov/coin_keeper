"""Gentle per-IP limits for anonymous catalog browsing."""

from __future__ import annotations

from fastapi import status

from app.api.errors import ProblemError
from app.core import rate_limit
from app.models import User


async def enforce_public_read(limit: rate_limit.RateLimit, user: User | None, ip: str) -> None:
    if user is not None:
        return
    try:
        await rate_limit.hit(limit, ip)
    except rate_limit.RateLimitExceededError as exc:
        raise ProblemError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate-limit-exceeded",
            "Too many requests",
            "Please continue browsing in a moment.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
