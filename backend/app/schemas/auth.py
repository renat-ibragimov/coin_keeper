"""Request and response bodies for /auth (docs/api.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from app.core.security import PASSWORD_MAX_LENGTH
from app.schemas.base import CamelModel

Locale = Literal["uk", "en"]


class RegisterRequest(CamelModel):
    email: EmailStr
    # Accepted for old clients during rollout, but deliberately ignored.
    password: str | None = None
    display_name: str | None = Field(default=None, max_length=200)
    # Honeypot: invisible to people, filled in by simple bots. A filled value
    # gets the same 202 as success and creates nothing. docs/auth.md.
    website: str | None = Field(default=None, max_length=200)


class LoginRequest(CamelModel):
    email: EmailStr
    # Wider than PASSWORD_MAX_LENGTH: passwords set before that cap existed
    # must still sign in; this only bounds the work argon2 is handed.
    password: str = Field(min_length=1, max_length=1024)


class EmailOnlyRequest(CamelModel):
    email: EmailStr


class VerifyEmailRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str | None = Field(default=None, max_length=PASSWORD_MAX_LENGTH)


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class SetPasswordRequest(CamelModel):
    new_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UpdateMeRequest(CamelModel):
    display_name: str | None = Field(default=None, max_length=200)
    locale: Locale | None = None


class UserOut(CamelModel):
    id: int
    email: str
    display_name: str | None
    role: str
    locale: str
    email_verified: bool
    has_password: bool
    google_linked: bool
    # A signed, short-lived URL, never the storage key: the bucket is private
    # and its host can change. Built by app.services.avatars.user_out, which
    # is the only place this model should be assembled.
    avatar_url: str | None = None


class TokensOut(CamelModel):
    """The refresh token is never in the body — it lives in an httpOnly cookie."""

    access_token: str
    expires_in: int


class SessionOut(CamelModel):
    user: UserOut
    tokens: TokensOut


class AcceptedOut(CamelModel):
    """Deliberately uninformative: the same answer whether the address exists."""

    status: Literal["accepted"] = "accepted"
