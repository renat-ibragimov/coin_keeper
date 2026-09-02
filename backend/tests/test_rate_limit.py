"""Rate limiting (docs/07-auth.md).

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
