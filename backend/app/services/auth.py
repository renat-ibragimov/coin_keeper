"""Authentication use cases.

Implements docs/07-auth.md: open registration with mandatory email
verification, argon2id passwords, short access tokens plus rotating refresh
tokens, and password recovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.mail import MailBackend, password_reset_email, verification_email
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import User
from app.models.enums import AuthTokenKind, UserRole
from app.repositories.users import (
    AuthTokenRepository,
    RefreshTokenRepository,
    UserRepository,
)

logger = logging.getLogger("app.auth")


class AuthError(Exception):
    """Base class for failures the API turns into problem responses."""


class InvalidCredentialsError(AuthError):
    """Wrong email or password. Deliberately indistinguishable between the two."""


class EmailNotVerifiedError(AuthError):
    """Correct password, but the address was never confirmed."""


class AccountDisabledError(AuthError):
    """Account exists and is verified but has been disabled by an admin."""


class InvalidOrExpiredTokenError(AuthError):
    pass


class RegistrationClosedError(AuthError):
    pass


class WeakPasswordError(AuthError):
    def __init__(self, min_length: int) -> None:
        super().__init__(f"password must be at least {min_length} characters")
        self.min_length = min_length


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings, mail: MailBackend) -> None:
        self._session = session
        self._settings = settings
        self._mail = mail
        self._users = UserRepository(session)
        self._refresh = RefreshTokenRepository(session)
        self._auth_tokens = AuthTokenRepository(session)

    # ---------------------------------------------------------------- passwords

    def _validate_password(self, password: str) -> None:
        """One rule for every path that sets a password.

        Registration, reset, change and the migration script all land here;
        there is no relaxed variant for seeding (docs/07-auth.md).
        """
        if len(password) < self._settings.password_min_length:
            raise WeakPasswordError(self._settings.password_min_length)

    # ------------------------------------------------------------- registration

    async def register(
        self, *, email: str, password: str, display_name: str | None, honeypot: str | None
    ) -> None:
        """Create an inactive account and send the verification email.

        Returns nothing on purpose: the caller always answers 202, so neither a
        bot nor a curious visitor learns whether the address was already taken.
        """
        if honeypot:
            # A person never fills this in. Answer as if all went well.
            logger.info("registration rejected by honeypot")
            return
        if not self._settings.allow_registration:
            raise RegistrationClosedError

        self._validate_password(password)

        existing = await self._users.get_by_email(email)
        if existing is not None:
            if existing.email_verified:
                # Do not leak the collision through the API; tell the owner of
                # the address instead, out of band.
                logger.info("registration attempt for an existing verified account")
                return
            # Unverified: treat as a repeated attempt and resend the link.
            await self._send_verification(existing)
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.USER,
            is_active=False,
            email_verified=False,
        )
        await self._users.add(user)
        await self._send_verification(user)

    async def resend_verification(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        if user is None or user.email_verified:
            return
        await self._send_verification(user)

    async def _send_verification(self, user: User) -> None:
        raw = generate_token()
        await self._auth_tokens.issue(
            user_id=user.id,
            kind=AuthTokenKind.EMAIL_VERIFY,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(hours=self._settings.email_verify_ttl_hours),
        )
        url = f"{self._settings.public_base_url}/verify-email?token={quote(raw)}"
        await self._mail.send(
            verification_email(user.email, url, self._settings.email_verify_ttl_hours)
        )

    async def verify_email(
        self, *, token: str, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        record = await self._auth_tokens.get_usable(
            token_hash=hash_token(token), kind=AuthTokenKind.EMAIL_VERIFY
        )
        if record is None:
            raise InvalidOrExpiredTokenError
        user = await self._users.get_by_id(record.user_id)
        if user is None:
            raise InvalidOrExpiredTokenError

        await self._auth_tokens.mark_used(record)
        user.email_verified = True
        user.is_active = True
        await self._session.flush()
        return await self._issue_session(user, user_agent=user_agent, ip=ip)

    # -------------------------------------------------------------------- login

    async def login(
        self, *, email: str, password: str, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError

        # Only past this point do we say anything specific: whoever knows the
        # password already knows the account exists, so telling them to confirm
        # the address leaks nothing while a wrong password still gets the
        # generic answer.
        if not user.email_verified:
            raise EmailNotVerifiedError
        if not user.is_active:
            raise AccountDisabledError

        return await self._issue_session(user, user_agent=user_agent, ip=ip)

    # ------------------------------------------------------------------ refresh

    async def refresh_session(
        self, *, refresh_token: str, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        """Rotate a refresh token, revoking the one presented."""
        record = await self._refresh.get_by_hash(hash_token(refresh_token))
        if record is None:
            raise InvalidOrExpiredTokenError

        if record.revoked_at is not None:
            # Reuse of a revoked token means it leaked: drop every session.
            await self._refresh.revoke_all_for_user(record.user_id)
            # Committed here, before raising. The request fails with an
            # exception, and the session dependency rolls back on the way out —
            # which would silently undo the revocation and leave the leaked
            # session working. This side effect has to outlive the error.
            await self._session.commit()
            logger.warning(
                "refresh token reuse detected, revoked all sessions for user %s",
                record.user_id,
            )
            raise InvalidOrExpiredTokenError

        if record.expires_at <= datetime.now(UTC):
            raise InvalidOrExpiredTokenError

        user = await self._users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise InvalidOrExpiredTokenError

        await self._refresh.revoke(record)
        return await self._issue_session(user, user_agent=user_agent, ip=ip)

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        record = await self._refresh.get_by_hash(hash_token(refresh_token))
        if record is not None and record.revoked_at is None:
            await self._refresh.revoke(record)

    async def _issue_session(
        self, user: User, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        raw_refresh = generate_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_ttl_days)
        await self._refresh.add(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        return IssuedSession(
            user=user,
            access_token=create_access_token(user.id),
            expires_in=self._settings.access_token_ttl_minutes * 60,
            refresh_token=raw_refresh,
            refresh_expires_at=expires_at,
        )

    # ----------------------------------------------------------------- password

    async def forgot_password(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        if user is None:
            return
        raw = generate_token()
        await self._auth_tokens.issue(
            user_id=user.id,
            kind=AuthTokenKind.PASSWORD_RESET,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(hours=self._settings.password_reset_ttl_hours),
        )
        url = f"{self._settings.public_base_url}/reset-password?token={quote(raw)}"
        await self._mail.send(
            password_reset_email(user.email, url, self._settings.password_reset_ttl_hours)
        )

    async def reset_password(self, *, token: str, new_password: str) -> None:
        self._validate_password(new_password)
        record = await self._auth_tokens.get_usable(
            token_hash=hash_token(token), kind=AuthTokenKind.PASSWORD_RESET
        )
        if record is None:
            raise InvalidOrExpiredTokenError
        user = await self._users.get_by_id(record.user_id)
        if user is None:
            raise InvalidOrExpiredTokenError

        await self._auth_tokens.mark_used(record)
        user.password_hash = hash_password(new_password)
        # A reset implies the account may have been compromised.
        await self._refresh.revoke_all_for_user(user.id)
        await self._session.flush()

    async def change_password(
        self, *, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError
        self._validate_password(new_password)
        user.password_hash = hash_password(new_password)
        await self._refresh.revoke_all_for_user(user.id)
        await self._session.flush()

    async def update_profile(
        self, *, user: User, display_name: str | None, locale: str | None
    ) -> User:
        if display_name is not None:
            user.display_name = display_name
        if locale is not None:
            user.locale = locale
            await self._users.set_settings_locale(user.id, locale)
        await self._session.flush()
        return user


__all__ = [
    "AccountDisabledError",
    "AuthError",
    "AuthService",
    "EmailNotVerifiedError",
    "InvalidCredentialsError",
    "InvalidOrExpiredTokenError",
    "IssuedSession",
    "RegistrationClosedError",
    "WeakPasswordError",
]
