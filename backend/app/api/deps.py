"""FastAPI dependencies: current user, services, client address."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ProblemError
from app.core.config import Settings, get_settings
from app.core.mail import MailBackend, get_mail_backend
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db_session
from app.models import User
from app.repositories.users import UserRepository
from app.services.auth import AuthService

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Mail = Annotated[MailBackend, Depends(get_mail_backend)]


def get_auth_service(session: DbSession, settings: AppSettings, mail: Mail) -> AuthService:
    return AuthService(session, settings, mail)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def client_ip(request: Request) -> str:
    """Caddy sits in front and sets X-Forwarded-For (docs/10-infra.md)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


ClientIp = Annotated[str, Depends(client_ip)]


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


UserAgent = Annotated[str | None, Depends(user_agent)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "not-authenticated",
            "Not authenticated",
            "An access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid-access-token",
            "Not authenticated",
            "The access token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid-access-token",
            "Not authenticated",
            "The access token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.email_verified:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "email-not-verified",
            "Forbidden",
            "Confirm your email address to use the service.",
        )
    if not user.is_active:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "account-disabled",
            "Forbidden",
            "This account is disabled.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
