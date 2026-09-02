"""Authentication endpoints (docs/03-api-contract.md, docs/07-auth.md)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import (
    AppSettings,
    AuthServiceDep,
    ClientIp,
    CurrentUser,
    UserAgent,
)
from app.api.errors import ProblemError
from app.core import rate_limit
from app.core.config import Settings
from app.schemas.auth import (
    AcceptedOut,
    ChangePasswordRequest,
    EmailOnlyRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    TokensOut,
    UpdateMeRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services.auth import (
    AccountDisabledError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    IssuedSession,
    RegistrationClosedError,
    WeakPasswordError,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH = "/api/v1/auth"


async def _enforce(limit: rate_limit.RateLimit, scope: str) -> None:
    try:
        await rate_limit.hit(limit, scope)
    except rate_limit.RateLimitExceededError as exc:
        raise ProblemError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate-limit-exceeded",
            "Too many requests",
            "Too many attempts. Try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


def _set_refresh_cookie(response: Response, session: IssuedSession, settings: Settings) -> None:
    """The refresh token only ever travels in an httpOnly cookie."""
    response.set_cookie(
        settings.refresh_cookie_name,
        session.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def _session_payload(session: IssuedSession) -> SessionOut:
    return SessionOut(
        user=UserOut.model_validate(session.user),
        tokens=TokensOut(access_token=session.access_token, expires_in=session.expires_in),
    )


def _weak_password_problem(exc: WeakPasswordError) -> ProblemError:
    return ProblemError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "weak-password",
        "Password rejected",
        f"The password must be at least {exc.min_length} characters long.",
    )


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(payload: RegisterRequest, service: AuthServiceDep, ip: ClientIp) -> AcceptedOut:
    """Always 202: the answer must not reveal whether the address is taken."""
    await _enforce(rate_limit.REGISTER, ip)
    try:
        await service.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            honeypot=payload.website,
        )
    except WeakPasswordError as exc:
        raise _weak_password_problem(exc) from exc
    except RegistrationClosedError as exc:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "registration-closed",
            "Forbidden",
            "Registration is currently closed.",
        ) from exc
    return AcceptedOut()


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    payload: EmailOnlyRequest, service: AuthServiceDep, ip: ClientIp
) -> AcceptedOut:
    await _enforce(rate_limit.RESEND_VERIFICATION, ip)
    await _enforce(rate_limit.RESEND_VERIFICATION, payload.email.lower())
    await service.resend_verification(payload.email)
    return AcceptedOut()


@router.post("/verify-email")
async def verify_email(
    payload: VerifyEmailRequest,
    response: Response,
    service: AuthServiceDep,
    settings: AppSettings,
    ip: ClientIp,
    agent: UserAgent,
) -> SessionOut:
    """Confirming the address activates the account and signs the user in."""
    try:
        session = await service.verify_email(token=payload.token, user_agent=agent, ip=ip)
    except InvalidOrExpiredTokenError as exc:
        raise ProblemError(
            status.HTTP_400_BAD_REQUEST,
            "invalid-verification-token",
            "Bad request",
            "This confirmation link is invalid or has already been used.",
        ) from exc
    _set_refresh_cookie(response, session, settings)
    return _session_payload(session)


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    settings: AppSettings,
    ip: ClientIp,
    agent: UserAgent,
) -> SessionOut:
    email_scope = payload.email.lower()
    await _enforce(rate_limit.LOGIN, ip)
    await _enforce(rate_limit.LOGIN, email_scope)
    try:
        session = await service.login(
            email=payload.email, password=payload.password, user_agent=agent, ip=ip
        )
    except InvalidCredentialsError as exc:
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid-credentials",
            "Not authenticated",
            "Invalid email or password.",
        ) from exc
    except EmailNotVerifiedError as exc:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "email-not-verified",
            "Forbidden",
            "Confirm your email address to activate the account.",
        ) from exc
    except AccountDisabledError as exc:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "account-disabled",
            "Forbidden",
            "This account is disabled.",
        ) from exc

    await rate_limit.reset(rate_limit.LOGIN, email_scope)
    await rate_limit.reset(rate_limit.LOGIN, ip)
    _set_refresh_cookie(response, session, settings)
    return _session_payload(session)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: AppSettings,
    ip: ClientIp,
    agent: UserAgent,
) -> SessionOut:
    """No request body: the token is read from the cookie."""
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "missing-refresh-token",
            "Not authenticated",
            "No refresh token was supplied.",
        )
    await _enforce(rate_limit.REFRESH, ip)
    try:
        session = await service.refresh_session(refresh_token=token, user_agent=agent, ip=ip)
    except InvalidOrExpiredTokenError as exc:
        _clear_refresh_cookie(response, settings)
        raise ProblemError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid-refresh-token",
            "Not authenticated",
            "The session has expired. Sign in again.",
        ) from exc
    _set_refresh_cookie(response, session, settings)
    return _session_payload(session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: AppSettings,
) -> None:
    await service.logout(request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response, settings)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: EmailOnlyRequest, service: AuthServiceDep, ip: ClientIp
) -> AcceptedOut:
    """Always 202, so the form cannot be used to probe for registered addresses."""
    await _enforce(rate_limit.FORGOT_PASSWORD, ip)
    await _enforce(rate_limit.FORGOT_PASSWORD, payload.email.lower())
    await service.forgot_password(payload.email)
    return AcceptedOut()


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest, service: AuthServiceDep, ip: ClientIp
) -> None:
    await _enforce(rate_limit.RESET_PASSWORD, ip)
    try:
        await service.reset_password(token=payload.token, new_password=payload.new_password)
    except WeakPasswordError as exc:
        raise _weak_password_problem(exc) from exc
    except InvalidOrExpiredTokenError as exc:
        raise ProblemError(
            status.HTTP_400_BAD_REQUEST,
            "invalid-reset-token",
            "Bad request",
            "This reset link is invalid or has already been used.",
        ) from exc


@router.get("/me")
async def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me")
async def update_me(
    payload: UpdateMeRequest, user: CurrentUser, service: AuthServiceDep
) -> UserOut:
    updated = await service.update_profile(
        user=user, display_name=payload.display_name, locale=payload.locale
    )
    return UserOut.model_validate(updated)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: CurrentUser,
    service: AuthServiceDep,
    settings: AppSettings,
) -> None:
    try:
        await service.change_password(
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except InvalidCredentialsError as exc:
        raise ProblemError(
            status.HTTP_400_BAD_REQUEST,
            "invalid-credentials",
            "Bad request",
            "The current password is incorrect.",
        ) from exc
    except WeakPasswordError as exc:
        raise _weak_password_problem(exc) from exc
    # Every session was revoked, including this one.
    _clear_refresh_cookie(response, settings)


__all__ = ["router"]
