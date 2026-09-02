"""Data access for users, sessions and one-time tokens."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthToken, RefreshToken, User, UserSettings
from app.models.enums import AuthTokenKind


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        self._session.add(UserSettings(user_id=user.id, locale=user.locale))
        await self._session.flush()
        return user

    async def set_settings_locale(self, user_id: int, locale: str) -> None:
        """Explicit UPDATE rather than touching User.settings.

        The relationship is lazy, and lazy loading from async code raises
        MissingGreenlet — the loader would do IO outside the greenlet context.
        """
        await self._session.execute(
            update(UserSettings).where(UserSettings.user_id == user_id).values(locale=locale)
        )
        await self._session.flush()


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: int) -> None:
        """Used on reuse of a revoked token and after a password reset."""
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self._session.flush()


class AuthTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(
        self, *, user_id: int, kind: AuthTokenKind, token_hash: str, expires_at: datetime
    ) -> AuthToken:
        """Issuing a token invalidates the user's earlier unused ones of that kind."""
        await self._session.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.kind == kind,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )
        token = AuthToken(user_id=user_id, kind=kind, token_hash=token_hash, expires_at=expires_at)
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_usable(self, *, token_hash: str, kind: AuthTokenKind) -> AuthToken | None:
        result = await self._session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash,
                AuthToken.kind == kind,
                AuthToken.used_at.is_(None),
                AuthToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: AuthToken) -> None:
        token.used_at = datetime.now(UTC)
        await self._session.flush()
