"""Request and response bodies for /auth (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.base import CamelModel

Locale = Literal["uk", "en"]


class RegisterRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1)
    display_name: str | None = Field(default=None, max_length=200)
    # Honeypot: invisible to people, filled in by simple bots. A filled value
    # gets the same 202 as success and creates nothing. docs/07-auth.md.
    website: str | None = Field(default=None, max_length=200)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1)


class EmailOnlyRequest(CamelModel):
    email: EmailStr


class VerifyEmailRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


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
