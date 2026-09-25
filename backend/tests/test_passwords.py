"""Password change and recovery (docs/auth.md)."""

from __future__ import annotations

import threading

import pytest
from argon2 import PasswordHasher
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.mail.base import EmailMessage
from app.core.mail.console import ConsoleMailBackend
from app.models import AuditLog, User
from app.repositories.users import UserRepository
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


async def test_a_missing_account_costs_a_password_check_too(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No account, or one without a password, must not answer faster than a
    wrong password: the check runs against a stand-in hash."""
    checks: list[str] = []
    real_verify = security.verify_password

    def counting_verify(password: str, password_hash: str) -> bool:
        checks.append(threading.current_thread().name)
        return real_verify(password, password_hash)

    monkeypatch.setattr(security, "verify_password", counting_verify)
    response = await client.post(
        "/api/v1/auth/login", json={"email": unique_email(), "password": "whatever-it-is"}
    )
    assert response.status_code == 401
    assert len(checks) == 1
    # And off the event loop: argon2 must not stall other requests.
    assert checks[0] != threading.main_thread().name


async def test_an_outdated_hash_is_upgraded_on_sign_in(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(PASSWORD)
    await db_session.execute(update(User).where(User.email == email).values(password_hash=weak))
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200

    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    await db_session.refresh(user)
    assert user.password_hash != weak
    assert not security.password_needs_rehash(user.password_hash)


async def test_an_overlong_new_password_is_rejected(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email = unique_email()
    await client.post("/api/v1/auth/register", json={"email": email})
    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": extract_token(mail_outbox), "newPassword": "x" * 257},
    )
    assert response.status_code == 422


async def test_a_mail_failure_answers_like_a_missing_account(
    client: AsyncClient, mail_outbox: list[EmailMessage], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mail goes out after the response: a failing mail server must not turn
    "this address has an account" into a 500 the other branch never gives."""
    email, _ = await register_and_verify(client, mail_outbox)

    async def broken_send(self: object, message: EmailMessage) -> None:
        raise ConnectionError("smtp down")

    monkeypatch.setattr(ConsoleMailBackend, "send", broken_send)
    existing = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    missing = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email()})
    assert existing.status_code == missing.status_code == 202


async def test_password_changes_are_audited(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> None:
    email, token = await register_and_verify(client, mail_outbox)
    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 204
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": extract_token(mail_outbox), "newPassword": PASSWORD},
    )

    user = await UserRepository(db_session).get_by_email(email)
    assert user is not None
    actions = (
        (await db_session.execute(select(AuditLog.action).where(AuditLog.user_id == user.id)))
        .scalars()
        .all()
    )
    assert sorted(actions) == ["password.changed", "password.reset"]
