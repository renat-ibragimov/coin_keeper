"""Rate limiting (docs/auth.md).

Enforced from day one: registration is open, so an unprotected login endpoint
would be brute-forced overnight.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.core import rate_limit
from app.core.mail.base import EmailMessage
from tests.helpers import PASSWORD, register_and_verify, unique_email


async def test_login_attempts_are_capped(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)

    for _ in range(rate_limit.LOGIN.limit):
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

    for _ in range(rate_limit.LOGIN.limit - 1):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    ).status_code == 200

    # The counter was reset, so a fresh run of wrong attempts is allowed again.
    for _ in range(rate_limit.LOGIN.limit):
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert response.status_code == 401


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
