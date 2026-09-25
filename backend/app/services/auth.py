"""Authentication use cases.

Implements docs/auth.md: open registration with mandatory email
verification, argon2id passwords, short access tokens plus rotating refresh
tokens, and password recovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.mail import MailBackend, password_reset_email, verification_email
from app.core.mail.base import EmailMessage
from app.core.security import (
    create_access_token,
    derive_successor_token,
    generate_token,
    hash_password_async,
    hash_token,
    password_needs_rehash,
    verify_password_async,
)
from app.models import AuditLog, RefreshToken, User
from app.models.enums import AuthTokenKind, RefreshRevokeReason, UserRole
from app.repositories.users import (
    AuthIdentityRepository,
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


class PasswordRequiredError(AuthError):
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
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        mail: MailBackend,
        background: BackgroundTasks | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._mail = mail
        self._background = background
        self._users = UserRepository(session)
        self._refresh = RefreshTokenRepository(session)
        self._auth_tokens = AuthTokenRepository(session)

    # ---------------------------------------------------------------- passwords

    def _validate_password(self, password: str) -> None:
        """One rule for every path that sets a password.

        Registration, reset, change and the migration script all land here;
        there is no relaxed variant for seeding (docs/auth.md).
        """
        if len(password) < self._settings.password_min_length:
            raise WeakPasswordError(self._settings.password_min_length)

    # ------------------------------------------------------------- registration

    async def register(
        self, *, email: str, password: str | None, display_name: str | None, honeypot: str | None
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

        existing = await self._users.get_by_email(email)
        if existing is not None:
            if existing.email_verified:
                # Do not leak the collision through the API; the attempt is
                # only logged.
                logger.info("registration attempt for an existing verified account")
                return
            # The mailbox owner chooses the password when consuming the link.
            await self._send_verification(existing)
            return

        user = User(
            email=email,
            password_hash=None,
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
        # The email must never contain a token that can be rolled back later.
        # If delivery fails, the inactive account remains and the user can resend.
        await self._session.commit()
        url = f"{self._settings.public_base_url}/verify-email?token={quote(raw)}"
        await self._deliver(
            verification_email(user.email, url, self._settings.email_verify_ttl_hours)
        )

    async def verify_email(
        self, *, token: str, new_password: str | None, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        record = await self._auth_tokens.get_usable(
            token_hash=hash_token(token), kind=AuthTokenKind.EMAIL_VERIFY, for_update=True
        )
        if record is None:
            raise InvalidOrExpiredTokenError
        user = await self._users.get_by_id(record.user_id)
        if user is None:
            raise InvalidOrExpiredTokenError

        # Confirming the mailbox always means choosing a password here: no
        # Google identity can stand in for it (docs/auth.md, "Google sign-in").
        if new_password is None:
            raise PasswordRequiredError
        self._validate_password(new_password)
        user.password_hash = await hash_password_async(new_password)
        if not user.email_verified:
            # Whatever Google identity an unconfirmed account carries was never
            # proven to belong to this mailbox's owner. They can link their own
            # Google in settings afterwards.
            await AuthIdentityRepository(self._session).unlink_all(user)

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
        password_hash = user.password_hash if user is not None else None
        if not await verify_password_async(password, password_hash) or user is None:
            raise InvalidCredentialsError
        assert user.password_hash is not None
        if password_needs_rehash(user.password_hash):
            # argon2 parameters changed since this hash was made.
            user.password_hash = await hash_password_async(password)

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
        """Rotate a refresh token within its family (docs/auth.md, "Sessions").

        The row is locked, so concurrent refreshes with the same token run one
        after another. A live token rotates into its deterministic successor.
        A token rotated less than the grace window ago gets that same successor
        back — a lost response or a second tab, not theft. A rotated token
        replayed later revokes its family only; other sign-ins survive.
        """
        now = datetime.now(UTC)
        record = await self._refresh.get_by_hash(hash_token(refresh_token), for_update=True)
        if record is None:
            raise InvalidOrExpiredTokenError
        successor_raw = derive_successor_token(refresh_token)

        if record.revoked_at is None:
            if record.expires_at <= now:
                raise InvalidOrExpiredTokenError
            user = await self._active_user(record.user_id)
            await self._refresh.revoke(record, RefreshRevokeReason.ROTATED)
            return await self._issue_session(
                user, user_agent=user_agent, ip=ip, parent=record, raw_refresh=successor_raw
            )

        if record.revoke_reason != RefreshRevokeReason.ROTATED:
            # Logged out, password changed, family already revoked: just dead.
            raise InvalidOrExpiredTokenError

        grace = timedelta(seconds=self._settings.refresh_reuse_grace_seconds)
        if now - record.revoked_at <= grace:
            successor = await self._refresh.get_by_hash(hash_token(successor_raw), for_update=True)
            if (
                successor is not None
                and successor.revoked_at is None
                and successor.expires_at > now
            ):
                user = await self._active_user(record.user_id)
                return IssuedSession(
                    user=user,
                    access_token=create_access_token(user.id, session_id=successor.family_id),
                    expires_in=self._settings.access_token_ttl_minutes * 60,
                    refresh_token=successor_raw,
                    refresh_expires_at=successor.expires_at,
                )

        if not await self._refresh.family_is_live(record.family_id, record.user_id):
            # The sign-in already ended (sign-out, a password change, an earlier
            # replay): nothing left to protect, and no alarm for a stale cookie.
            raise InvalidOrExpiredTokenError

        # A rotated token came back too late, or after its successor moved on:
        # it leaked. End this sign-in, not the user's other devices.
        await self._refresh.revoke_family(record.family_id, RefreshRevokeReason.REUSE)
        self._session.add(
            AuditLog(
                user_id=record.user_id,
                action="session.refresh_reuse",
                entity_type="refresh_token_family",
                entity_id=str(record.family_id),
                details={"ip": ip, "user_agent": user_agent},
            )
        )
        # Committed here, before raising. The request fails with an exception,
        # and the session dependency rolls back on the way out — which would
        # silently undo the revocation and leave the leaked session working.
        await self._session.commit()
        logger.warning(
            "refresh token reuse detected, revoked family %s of user %s",
            record.family_id,
            record.user_id,
        )
        raise InvalidOrExpiredTokenError

    async def logout(self, refresh_token: str | None) -> None:
        """Ends this sign-in only: the whole family, whichever of its tokens
        the browser still holds."""
        if not refresh_token:
            return
        record = await self._refresh.get_by_hash(hash_token(refresh_token))
        if record is not None:
            await self._refresh.revoke_family(record.family_id, RefreshRevokeReason.LOGOUT)

    async def _active_user(self, user_id: int) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidOrExpiredTokenError
        return user

    async def _issue_session(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip: str | None,
        parent: RefreshToken | None = None,
        raw_refresh: str | None = None,
    ) -> IssuedSession:
        """A new sign-in (no `parent`) starts a family with a random token; a
        rotation continues the parent's family with its derived successor."""
        raw_refresh = raw_refresh or generate_token()
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_ttl_days)
        token = await self._refresh.add(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
            parent=parent,
        )
        return IssuedSession(
            user=user,
            access_token=create_access_token(user.id, session_id=token.family_id),
            expires_in=self._settings.access_token_ttl_minutes * 60,
            refresh_token=raw_refresh,
            refresh_expires_at=expires_at,
        )

    async def issue_session_for_user(
        self, user: User, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        if not user.is_active or not user.email_verified:
            raise AccountDisabledError
        return await self._issue_session(user, user_agent=user_agent, ip=ip)

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
        await self._session.commit()
        url = f"{self._settings.public_base_url}/reset-password?token={quote(raw)}"
        await self._deliver(
            password_reset_email(user.email, url, self._settings.password_reset_ttl_hours)
        )

    async def _deliver(self, message: EmailMessage) -> None:
        """Send after the response, never inside it: an SMTP round trip only on
        the "account exists" branch would tell a stranger which addresses are
        registered, by time or by a 500 when mail fails (docs/auth.md)."""
        if self._background is None:
            await self._send_logged(message)
        else:
            self._background.add_task(self._send_logged, message)

    async def _send_logged(self, message: EmailMessage) -> None:
        try:
            await self._mail.send(message)
        except Exception:
            # The token is already committed; the user can ask for a resend.
            logger.exception("sending %r failed", message.subject)

    async def reset_password(self, *, token: str, new_password: str) -> None:
        self._validate_password(new_password)
        record = await self._auth_tokens.get_usable(
            token_hash=hash_token(token), kind=AuthTokenKind.PASSWORD_RESET, for_update=True
        )
        if record is None:
            raise InvalidOrExpiredTokenError
        user = await self._users.get_by_id(record.user_id)
        if user is None:
            raise InvalidOrExpiredTokenError

        await self._auth_tokens.mark_used(record)
        user.password_hash = await hash_password_async(new_password)
        self._audit(user, "password.reset")
        # A reset implies the account may have been compromised.
        await self._refresh.revoke_all_for_user(user.id, RefreshRevokeReason.PASSWORD_RESET)
        await self._session.flush()

    async def change_password(
        self,
        *,
        user: User,
        current_password: str,
        new_password: str,
        user_agent: str | None,
        ip: str | None,
    ) -> IssuedSession:
        """Ends every sign-in — whoever else may know the old password — and
        starts a fresh one for the device that made the change, so it isn't
        thrown out right after a successful action."""
        if not await verify_password_async(current_password, user.password_hash):
            raise InvalidCredentialsError
        self._validate_password(new_password)
        user.password_hash = await hash_password_async(new_password)
        self._audit(user, "password.changed")
        await self._refresh.revoke_all_for_user(user.id, RefreshRevokeReason.PASSWORD_CHANGE)
        return await self._issue_session(user, user_agent=user_agent, ip=ip)

    async def set_password(self, *, user: User, new_password: str) -> None:
        """Add a password to a verified Google-only account, without another user."""
        if user.password_hash is not None:
            raise InvalidCredentialsError
        self._validate_password(new_password)
        user.password_hash = await hash_password_async(new_password)
        self._audit(user, "password.set")
        await self._session.flush()

    def _audit(self, user: User, action: str) -> None:
        """A change to how the account signs in, kept for the owner to review
        after a compromise (docs/auth.md, "Security events")."""
        self._session.add(
            AuditLog(user_id=user.id, action=action, entity_type="user", entity_id=str(user.id))
        )

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
    "PasswordRequiredError",
    "RegistrationClosedError",
    "WeakPasswordError",
]
