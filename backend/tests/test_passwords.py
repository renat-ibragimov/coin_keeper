"""Password change and recovery (docs/07-auth.md)."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.mail.base import EmailMessage
from tests.helpers import PASSWORD, extract_token, register_and_verify, unique_email

NEW_PASSWORD = "another-long-password"


async def test_forgot_and_reset_password(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)

    requested = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert requested.status_code == 202

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": extract_token(mail_outbox), "newPassword": NEW_PASSWORD},
    )
    assert reset.status_code == 204

    old = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert old.status_code == 401

    new = await client.post("/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert new.status_code == 200


async def test_reset_revokes_existing_sessions(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)
    # The session opened by verification must not survive a password reset.
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": extract_token(mail_outbox), "newPassword": NEW_PASSWORD},
    )
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_reset_token_is_single_use(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    token = extract_token(mail_outbox)

    first = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "newPassword": NEW_PASSWORD},
    )
    assert first.status_code == 204

    second = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "newPassword": "yet-another-password"},
    )
    assert second.status_code == 400


async def test_reset_rejects_a_weak_password(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": extract_token(mail_outbox), "newPassword": "short"},
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("weak-password")


async def test_forgot_password_for_unknown_address_looks_identical(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    known, _ = await register_and_verify(client, mail_outbox)
    mail_outbox.clear()

    for address in (known, unique_email()):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": address})
        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}

    # Only the real account got a message; the response gave nothing away.
    assert [message.to for message in mail_outbox] == [known]


async def test_change_password(client: AsyncClient, mail_outbox: list[EmailMessage]) -> None:
    email, access = await register_and_verify(client, mail_outbox)
    auth = {"Authorization": f"Bearer {access}"}

    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": "not-the-password", "newPassword": NEW_PASSWORD},
        headers=auth,
    )
    assert wrong.status_code == 400

    weak = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": "short"},
        headers=auth,
    )
    assert weak.status_code == 422

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD},
        headers=auth,
    )
    assert changed.status_code == 204

    # Sessions were revoked along with the change.
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD})
    ).status_code == 200
