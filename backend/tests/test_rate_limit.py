"""Rate limiting (docs/auth.md).

Enforced from day one: registration is open, so an unprotected login endpoint
would be brute-forced overnight.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.core import rate_limit
from app.core.mail.base import EmailMessage
from app.core.rate_limit import get_redis
from tests.helpers import PASSWORD, register_and_verify, unique_email


async def test_login_attempts_are_capped(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)

    for _ in range(rate_limit.LOGIN_EMAIL.limit):
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/problem+json")
    assert int(blocked.headers["Retry-After"]) > 0

    # Even the correct password is refused while the window is full.
    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    ).status_code == 429


async def test_successful_login_clears_the_counter(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)

    for _ in range(rate_limit.LOGIN_EMAIL.limit - 1):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    ).status_code == 200

    # The counter was reset, so a fresh run of wrong attempts is allowed again.
    for _ in range(rate_limit.LOGIN_EMAIL.limit):
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert response.status_code == 401


async def test_a_successful_login_does_not_reset_the_ip_counter(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    """Signing into one's own account between guesses at other people's emails
    must not buy more guesses from the same address."""
    own_email, _ = await register_and_verify(client, mail_outbox)
    for attempt in range(rate_limit.LOGIN_IP.limit):
        if attempt % 4 == 3:
            payload = {"email": own_email, "password": PASSWORD}
        else:
            payload = {"email": unique_email(), "password": "wrong-password"}
        assert (await client.post("/api/v1/auth/login", json=payload)).status_code != 429

    blocked = await client.post(
        "/api/v1/auth/login", json={"email": unique_email(), "password": "wrong-password"}
    )
    assert blocked.status_code == 429


async def test_a_counter_left_without_expiry_gets_one(redis_client: None) -> None:
    """A counter that lost its expiry (a crash between two calls) would refuse
    forever; the next hit gives it the window back."""
    key = f"rl:{rate_limit.LOGIN_EMAIL.name}:stuck@example.com"
    await get_redis().set(key, rate_limit.LOGIN_EMAIL.limit + 5)
    try:
        await rate_limit.hit(rate_limit.LOGIN_EMAIL, "stuck@example.com")
    except rate_limit.RateLimitExceededError as exc:
        assert exc.retry_after_seconds > 1
    ttl = await get_redis().ttl(key)
    assert 0 < ttl <= rate_limit.LOGIN_EMAIL.window_seconds


async def test_registration_attempts_are_capped(client: AsyncClient) -> None:
    for _ in range(rate_limit.REGISTER.limit):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": unique_email(), "password": PASSWORD},
        )
        assert response.status_code == 202

    blocked = await client.post(
        "/api/v1/auth/register", json={"email": unique_email(), "password": PASSWORD}
    )
    assert blocked.status_code == 429


async def test_forgot_password_attempts_are_capped(client: AsyncClient) -> None:
    email = unique_email()
    for _ in range(rate_limit.FORGOT_PASSWORD.limit):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 202

    blocked = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert blocked.status_code == 429


async def test_public_catalog_limit_only_applies_to_guests(
    client: AsyncClient, mail_outbox: list[EmailMessage], monkeypatch
) -> None:
    from app.core.rate_limit import RateLimit

    monkeypatch.setattr(rate_limit, "PUBLIC_CATALOG", RateLimit("test_public_catalog", 2, 60))
    headers = {"X-Forwarded-For": "192.0.2.42"}
    for _ in range(2):
        assert (await client.get("/api/v1/catalog", headers=headers)).status_code == 200
    blocked = await client.get("/api/v1/catalog", headers=headers)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0

    _, token = await register_and_verify(client, mail_outbox)
    authenticated = await client.get(
        "/api/v1/catalog", headers={**headers, "Authorization": f"Bearer {token}"}
    )
    assert authenticated.status_code == 200
    assert (await client.get("/api/v1/catalog?q=Ukraine", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/countries", headers=headers)).status_code == 200
