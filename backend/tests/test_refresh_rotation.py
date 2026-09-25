"""Refresh token rotation, the grace window and family-scoped reuse detection
(docs/auth.md, "Sessions")."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import jwt
from httpx import AsyncClient, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.mail.base import EmailMessage
from app.core.mail.console import ConsoleMailBackend
from app.core.security import generate_token, hash_token
from app.models import AuditLog, RefreshToken, User
from app.repositories.users import RefreshTokenRepository
from app.services.auth import AuthService
from tests.helpers import PASSWORD, register_and_verify, unique_email

REFRESH_COOKIE = "coinkeeper_refresh"


async def _refresh_with(client: AsyncClient, token: str) -> Response:
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
    return response


async def _sign_in_again(client: AsyncClient, email: str) -> str:
    """A second sign-in — another device — and its refresh token. The jar is
    emptied first: two cookies of the same name in it make it ambiguous."""
    client.cookies.clear()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.cookies[REFRESH_COOKIE]


async def _age_rotation(db_session: AsyncSession, token: str, seconds: int) -> None:
    """Pretend `token` was rotated `seconds` ago."""
    await db_session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(token))
        .values(revoked_at=RefreshToken.revoked_at - timedelta(seconds=seconds))
    )
    await db_session.commit()


async def _reuse_events(db_session: AsyncSession) -> int:
    return (
        await db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.action == "session.refresh_reuse")
        )
    ).scalar_one()


async def test_refresh_rotates_the_token(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    await register_and_verify(client, mail_outbox)
    first = client.cookies[REFRESH_COOKIE]

    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200

    second = client.cookies[REFRESH_COOKIE]
    assert second != first


async def test_a_replay_within_the_grace_window_gets_the_same_successor(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    """A lost response or a second tab: the old token comes back moments after
    rotating, and gets the very token the first response carried."""
    await register_and_verify(client, mail_outbox)
    first = client.cookies[REFRESH_COOKIE]

    rotated = await _refresh_with(client, first)
    assert rotated.status_code == 200
    successor = rotated.cookies[REFRESH_COOKIE]

    replayed = await _refresh_with(client, first)
    assert replayed.status_code == 200
    assert replayed.cookies[REFRESH_COOKIE] == successor
    assert replayed.json()["tokens"]["accessToken"]

    # Still one live token in the family, and it keeps rotating normally.
    assert (await _refresh_with(client, successor)).status_code == 200


async def test_a_late_replay_ends_only_its_own_sign_in(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> None:
    """Past the grace window a rotated token is treated as leaked: its family
    dies and the event is audited, while the user's other device stays signed
    in (the owner was logged out of desktop and phone at once before)."""
    email, _ = await register_and_verify(client, mail_outbox)
    desktop_old = client.cookies[REFRESH_COOKIE]
    desktop_current = (await _refresh_with(client, desktop_old)).cookies[REFRESH_COOKIE]
    phone = await _sign_in_again(client, email)

    await _age_rotation(db_session, desktop_old, seconds=60)

    assert (await _refresh_with(client, desktop_old)).status_code == 401
    assert (await _refresh_with(client, desktop_current)).status_code == 401
    assert (await _refresh_with(client, phone)).status_code == 200
    assert await _reuse_events(db_session) == 1


async def test_a_replay_after_the_successor_moved_on_is_theft(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> None:
    """Within the window only the direct successor is handed out again; a token
    two rotations back means someone else holds an old copy."""
    await register_and_verify(client, mail_outbox)
    first = client.cookies[REFRESH_COOKIE]
    second = (await _refresh_with(client, first)).cookies[REFRESH_COOKIE]
    third = (await _refresh_with(client, second)).cookies[REFRESH_COOKIE]

    assert (await _refresh_with(client, first)).status_code == 401
    assert (await _refresh_with(client, third)).status_code == 401
    assert await _reuse_events(db_session) == 1


async def test_a_logged_out_token_is_just_dead(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> None:
    """Signing out ends that sign-in only; its token coming back later is a
    plain 401, not an alarm, and the other device is untouched."""
    email, _ = await register_and_verify(client, mail_outbox)
    laptop = client.cookies[REFRESH_COOKIE]
    phone = await _sign_in_again(client, email)

    client.cookies.clear()
    logout = await client.post(
        "/api/v1/auth/logout", headers={"Cookie": f"{REFRESH_COOKIE}={laptop}"}
    )
    assert logout.status_code == 204

    assert (await _refresh_with(client, laptop)).status_code == 401
    assert (await _refresh_with(client, phone)).status_code == 200
    assert await _reuse_events(db_session) == 0


async def test_refresh_without_a_cookie_is_unauthorised(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


async def test_concurrent_refreshes_share_one_successor(engine: AsyncEngine) -> None:
    """Two tabs refresh with the same cookie at the same moment, each on its own
    connection: the row lock makes the second wait and take the grace path, so
    both get the same token and the family never forks. Real commits here, so
    the rows are removed at the end."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    raw = generate_token()
    async with factory() as session:
        user = User(email=unique_email(), email_verified=True, is_active=True)
        session.add(user)
        await session.flush()
        await RefreshTokenRepository(session).add(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            user_agent=None,
            ip=None,
        )
        await session.commit()
        user_id = user.id

    async def refresh_once() -> str:
        async with factory() as session:
            issued = await AuthService(
                session, get_settings(), ConsoleMailBackend()
            ).refresh_session(refresh_token=raw, user_agent=None, ip=None)
            await session.commit()
            return issued.refresh_token

    try:
        first, second = await asyncio.gather(refresh_once(), refresh_once())
        assert first == second
        async with factory() as session:
            live = (
                await session.execute(
                    select(func.count(RefreshToken.id)).where(
                        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
                    )
                )
            ).scalar_one()
        assert live == 1
    finally:
        async with factory() as session:
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()


async def test_signing_out_ends_the_access_token_at_once(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    """An access token belongs to its sign-in: after logout it stops working
    immediately instead of living out its 15 minutes."""
    _, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_a_password_change_ends_other_devices_access_tokens(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    email, laptop_token = await register_and_verify(client, mail_outbox)
    client.cookies.clear()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    phone_token = login.json()["tokens"]["accessToken"]

    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": "another-long-password"},
        headers={"Authorization": f"Bearer {phone_token}"},
    )
    assert changed.status_code == 200
    laptop = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {laptop_token}"}
    )
    assert laptop.status_code == 401


async def test_an_access_token_without_a_session_is_refused(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    """Tokens issued before sessions were carried (or forged without one) are
    refused; the client refreshes and gets one that carries it."""
    _, token = await register_and_verify(client, mail_outbox)
    claims = jwt.decode(token, options={"verify_signature": False})
    del claims["sid"]
    legacy = jwt.encode(claims, get_settings().jwt_secret, algorithm="HS256")
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"})
    assert response.status_code == 401
