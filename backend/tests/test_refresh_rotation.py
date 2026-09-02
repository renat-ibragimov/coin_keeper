"""Refresh token rotation and reuse detection (docs/07-auth.md)."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.mail.base import EmailMessage
from tests.helpers import PASSWORD, register_and_verify

REFRESH_COOKIE = "coinkeeper_refresh"


async def _refresh_with(client: AsyncClient, token: str) -> int:
    """Send exactly one refresh cookie, bypassing the client cookie jar.

    The jar keys cookies by domain and path, so setting one by hand leaves two
    entries with the same name and the request becomes ambiguous.
    """
    saved = dict(client.cookies)
    client.cookies.clear()
    try:
        response = await client.post(
            "/api/v1/auth/refresh", headers={"Cookie": f"{REFRESH_COOKIE}={token}"}
        )
    finally:
        client.cookies.clear()
        for name, value in saved.items():
            client.cookies.set(name, value, domain="testserver")
    return response.status_code


async def test_refresh_rotates_the_token(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    await register_and_verify(client, mail_outbox)
    first = client.cookies[REFRESH_COOKIE]

    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200

    second = client.cookies[REFRESH_COOKIE]
    assert second != first


async def test_reusing_a_revoked_token_kills_every_session(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)
    stolen = client.cookies[REFRESH_COOKIE]

    # Legitimate rotation revokes `stolen` and issues a fresh token.
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    current = client.cookies[REFRESH_COOKIE]
    assert current != stolen

    # An attacker replays the revoked token.
    assert await _refresh_with(client, stolen) == 401

    # The legitimate session is gone too: reuse means the token leaked, so
    # every session of that user is revoked.
    assert await _refresh_with(client, current) == 401

    # Signing in again works and issues a usable session.
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200


async def test_refresh_without_a_cookie_is_unauthorised(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
