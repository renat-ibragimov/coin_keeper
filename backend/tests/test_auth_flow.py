"""The full signup path: register, verify, sign in, rotate, sign out."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.mail.base import EmailMessage
from tests.helpers import PASSWORD, extract_token, register_and_verify, unique_email

REFRESH_COOKIE = "coinkeeper_refresh"


async def test_registration_verification_login_refresh_logout(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email = unique_email()

    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "displayName": "Test Person"},
    )
    assert registered.status_code == 202
    assert registered.json() == {"status": "accepted"}

    # The account exists but cannot be used until the address is confirmed.
    blocked = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert blocked.status_code == 403
    assert blocked.json()["type"].endswith("email-not-verified")

    verified = await client.post(
        "/api/v1/auth/verify-email", json={"token": extract_token(mail_outbox)}
    )
    assert verified.status_code == 200
    body = verified.json()
    assert body["user"]["email"] == email
    assert body["user"]["emailVerified"] is True
    assert body["user"]["locale"] == "uk"
    assert body["tokens"]["accessToken"]
    # The refresh token travels only in the cookie, never in the body.
    assert "refreshToken" not in body["tokens"]
    assert REFRESH_COOKIE in verified.cookies

    logged_in = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert logged_in.status_code == 200
    access = logged_in.json()["tokens"]["accessToken"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    assert rotated.json()["tokens"]["accessToken"]

    logged_out = await client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 204

    after_logout = await client.post("/api/v1/auth/refresh")
    assert after_logout.status_code == 401


async def test_verification_token_is_single_use(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email = unique_email()
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = extract_token(mail_outbox)

    assert (
        await client.post("/api/v1/auth/verify-email", json={"token": token})
    ).status_code == 200
    replayed = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert replayed.status_code == 400


async def test_honeypot_silently_rejects_registration(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email = unique_email()
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "website": "http://spam.example.com"},
    )
    # Same answer as success, but nothing was created and no mail was sent.
    assert response.status_code == 202
    assert not any(message.to == email for message in mail_outbox)

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 401


async def test_login_does_not_reveal_whether_the_address_exists(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)

    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password-here"}
    )
    unknown_address = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email(), "password": "wrong-password-here"},
    )

    assert wrong_password.status_code == unknown_address.status_code == 401
    assert wrong_password.json()["detail"] == unknown_address.json()["detail"]


async def test_unauthenticated_me_returns_problem_json(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) >= {"type", "title", "status", "detail"}


@pytest.mark.parametrize("password", ["short", "123456789"])
async def test_password_shorter_than_ten_characters_is_rejected(
    client: AsyncClient, password: str
) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": unique_email(), "password": password}
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("weak-password")


async def test_update_profile_changes_display_name_and_locale(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    _, access = await register_and_verify(client, mail_outbox)
    response = await client.patch(
        "/api/v1/auth/me",
        json={"displayName": "Renamed", "locale": "en"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    assert response.json()["displayName"] == "Renamed"
    assert response.json()["locale"] == "en"
