"""Data access for users, sessions and one-time tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthIdentity, AuthToken, RefreshToken, User, UserSettings
from app.models.enums import AuthTokenKind, RefreshRevokeReason


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

    async def update_settings(self, user_id: int, **fields: object) -> None:
        """Generic partial update: pass only the `user_settings` columns that
        changed. Keeps adding a new setting (currency, storage locations, …)
        a one-line change in the schema rather than a new repository method
        each time."""
        if not fields:
            return
        await self._session.execute(
            update(UserSettings).where(UserSettings.user_id == user_id).values(**fields)
        )
        await self._session.flush()

    async def get_settings(self, user_id: int) -> UserSettings | None:
        result = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()


class AuthIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_google(self, subject: str) -> AuthIdentity | None:
        result = await self._session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "google", AuthIdentity.subject == subject
            )
        )
        return result.scalar_one_or_none()

    async def link_google(self, user: User, *, subject: str, email: str) -> AuthIdentity:
        identity = AuthIdentity(
            user_id=user.id, provider="google", subject=subject, email_at_link=email
        )
        self._session.add(identity)
        await self._session.flush()
        await self._session.refresh(user, ["identities"])
        return identity

    async def unlink_all(self, user: User) -> None:
        await self._session.execute(delete(AuthIdentity).where(AuthIdentity.user_id == user.id))
        await self._session.flush()
        await self._session.refresh(user, ["identities"])


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
        parent: RefreshToken | None = None,
    ) -> RefreshToken:
        """A new sign-in starts a family; a rotation (`parent`) continues it."""
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
            family_id=parent.family_id if parent else uuid.uuid4(),
            parent_id=parent.id if parent else None,
            session_started_at=parent.session_started_at if parent else datetime.now(UTC),
            persistent=parent.persistent if parent else True,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshToken | None:
        """`for_update` serialises concurrent refreshes of the same token."""
        query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        if for_update:
            query = query.with_for_update()
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken, reason: RefreshRevokeReason) -> None:
        token.revoked_at = datetime.now(UTC)
        token.revoke_reason = reason
        await self._session.flush()

    async def revoke_family(self, family_id: uuid.UUID, reason: RefreshRevokeReason) -> None:
        """Ends one sign-in: logout, or a proven replay of a rotated token."""
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoke_reason=reason)
        )
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: int, reason: RefreshRevokeReason) -> None:
        """Ends every sign-in of the user: password change or reset."""
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoke_reason=reason)
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

    async def get_usable(
        self, *, token_hash: str, kind: AuthTokenKind, for_update: bool = False
    ) -> AuthToken | None:
        statement = select(AuthToken).where(
            AuthToken.token_hash == token_hash,
            AuthToken.kind == kind,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > datetime.now(UTC),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def mark_used(self, token: AuthToken) -> None:
        token.used_at = datetime.now(UTC)
        await self._session.flush()
