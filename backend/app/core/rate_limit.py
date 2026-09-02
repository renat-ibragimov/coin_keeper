"""Redis-backed fixed-window rate limiting.

Limits are the table in docs/07-auth.md. With registration open from day one
this is a release condition, not a later addition: an open service without it
gets brute-forced overnight.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None


@dataclass(frozen=True, slots=True)
class RateLimit:
    """`limit` attempts per `window_seconds`."""

    name: str
    limit: int
    window_seconds: int


HOUR = 3600

LOGIN = RateLimit("login", limit=5, window_seconds=15 * 60)
REGISTER = RateLimit("register", limit=3, window_seconds=HOUR)
REFRESH = RateLimit("refresh", limit=30, window_seconds=HOUR)
FORGOT_PASSWORD = RateLimit("forgot_password", limit=3, window_seconds=HOUR)
RESEND_VERIFICATION = RateLimit("resend_verification", limit=3, window_seconds=HOUR)
RESET_PASSWORD = RateLimit("reset_password", limit=5, window_seconds=HOUR)


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


async def hit(limit: RateLimit, scope: str) -> None:
    """Count one attempt against `scope`, raising once the window is full.

    `scope` is what the limit is applied to: an IP address, an email address or
    a user id. Several scopes per endpoint are normal, see docs/07-auth.md.
    """
    redis = get_redis()
    key = f"rl:{limit.name}:{scope}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, limit.window_seconds)
    if count > limit.limit:
        ttl = await redis.ttl(key)
        raise RateLimitExceededError(max(ttl, 1))


async def reset(limit: RateLimit, scope: str) -> None:
    """Drop the counter, used after a successful login."""
    await get_redis().delete(f"rl:{limit.name}:{scope}")
