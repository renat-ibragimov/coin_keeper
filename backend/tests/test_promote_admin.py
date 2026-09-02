"""The promote_admin script (docs/09-data-migration.md)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.models.enums import UserRole
from scripts.promote_admin import EXIT_NOT_FOUND, EXIT_NOT_VERIFIED, EXIT_OK, _apply
from tests.helpers import unique_email


async def _add_user(session: AsyncSession, *, verified: bool) -> User:
    user = User(
        email=unique_email(),
        password_hash="not-a-real-hash",
        role=UserRole.USER,
        is_active=verified,
        email_verified=verified,
    )
    session.add(user)
    await session.flush()
    return user


async def test_promotes_a_verified_user(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, verified=True)

    assert await _apply(db_session, user.email, demote=False) == EXIT_OK
    await db_session.refresh(user)
    assert user.role is UserRole.ADMIN

    logged = await db_session.execute(select(AuditLog).where(AuditLog.user_id == user.id))
    entry = logged.scalar_one()
    assert entry.action == "role.promote"
    assert entry.details == {"from": "user", "to": "admin"}


async def test_promotion_is_idempotent(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, verified=True)
    assert await _apply(db_session, user.email, demote=False) == EXIT_OK
    # A second run must not fail, and must not write a second audit entry.
    assert await _apply(db_session, user.email, demote=False) == EXIT_OK

    entries = await db_session.execute(select(AuditLog).where(AuditLog.user_id == user.id))
    assert len(entries.scalars().all()) == 1


async def test_demote_reverses_the_role(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, verified=True)
    await _apply(db_session, user.email, demote=False)
    assert await _apply(db_session, user.email, demote=True) == EXIT_OK
    await db_session.refresh(user)
    assert user.role is UserRole.USER


async def test_unverified_user_is_not_promoted(db_session: AsyncSession) -> None:
    """An unconfirmed address must not be handed admin rights."""
    user = await _add_user(db_session, verified=False)
    assert await _apply(db_session, user.email, demote=False) == EXIT_NOT_VERIFIED
    await db_session.refresh(user)
    assert user.role is UserRole.USER


async def test_unknown_address_reports_not_found(db_session: AsyncSession) -> None:
    assert await _apply(db_session, unique_email(), demote=False) == EXIT_NOT_FOUND
