"""Google sign-in and explicit account linking."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import AppSettings, ClientIp, CurrentUser, DbSession, Mail, Telegram, UserAgent
from app.api.errors import ProblemError
from app.api.v1.auth import _enforce, _set_refresh_cookie
from app.core import rate_limit
from app.models import AuditLog, User
from app.models.enums import UserRole
from app.repositories.users import AuthIdentityRepository, UserRepository
from app.services.auth import AuthService
from app.services.google_auth import STATE_COOKIE, GoogleOAuth, GoogleOAuthError
from app.services.telegram import queue_new_user_notification

router = APIRouter(prefix="/auth/google", tags=["auth"])


def _oauth(settings: AppSettings) -> GoogleOAuth:
    return GoogleOAuth(settings, rate_limit.get_redis())


def _state_cookie(response: Response, state: str, settings: AppSettings) -> None:
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth/google",
    )


def _clear_state_cookie(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(STATE_COOKIE, path="/api/v1/auth/google", secure=settings.cookie_secure)


def _return_to_app(settings: AppSettings, destination: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.public_base_url.rstrip('/')}{destination}", status_code=303)


@router.get("/status")
async def google_status(settings: AppSettings) -> dict[str, bool]:
    return {"enabled": _oauth(settings).enabled}


@router.get("/start")
async def start_login(settings: AppSettings, ip: ClientIp) -> RedirectResponse:
    await _enforce(rate_limit.GOOGLE_START, ip)
    try:
        flow = await _oauth(settings).start(mode="login")
    except GoogleOAuthError as exc:
        raise ProblemError(
            503, "google-disabled", "Unavailable", "Google sign-in is unavailable."
        ) from exc
    response = RedirectResponse(flow.url, status_code=302)
    _state_cookie(response, flow.state, settings)
    return response


@router.post("/link/start")
async def start_link(user: CurrentUser, settings: AppSettings, ip: ClientIp) -> JSONResponse:
    await _enforce(rate_limit.GOOGLE_START, ip)
    if user.google_linked:
        raise ProblemError(409, "google-already-linked", "Conflict", "Google is already linked.")
    try:
        flow = await _oauth(settings).start(mode="link", user_id=user.id)
    except GoogleOAuthError as exc:
        raise ProblemError(
            503, "google-disabled", "Unavailable", "Google sign-in is unavailable."
        ) from exc
    response = JSONResponse({"url": flow.url})
    _state_cookie(response, flow.state, settings)
    return response


@router.get("/callback")
async def callback(
    request: Request,
    settings: AppSettings,
    session: DbSession,
    mail: Mail,
    sender: Telegram,
    background: BackgroundTasks,
    ip: ClientIp,
    agent: UserAgent,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    oauth = _oauth(settings)
    mode = "login"
    try:
        flow = await oauth.consume(state=state, cookie_state=request.cookies.get(STATE_COOKIE))
        mode = flow.mode
        if error or not code:
            raise GoogleOAuthError("Google authorization was cancelled")
        claims = await oauth.exchange(code=code, flow=flow)
    except GoogleOAuthError:
        response = _return_to_app(
            settings,
            "/google-complete?mode=link&google=error" if mode == "link" else "/login?google=error",
        )
        _clear_state_cookie(response, settings)
        return response

    users = UserRepository(session)
    identities = AuthIdentityRepository(session)
    existing_identity = await identities.get_google(claims.subject)

    if flow.mode == "link":
        user = await users.get_by_id(flow.user_id) if flow.user_id is not None else None
        if (
            user is None
            or not user.is_active
            or not user.email_verified
            or user.email.lower() != claims.email.lower()
            or (existing_identity is not None and existing_identity.user_id != user.id)
            or (user.google_linked and existing_identity is None)
        ):
            destination = "/google-complete?mode=link&google=conflict"
        else:
            if existing_identity is None:
                await identities.link_google(user, subject=claims.subject, email=claims.email)
                session.add(
                    AuditLog(
                        user_id=user.id,
                        action="google.linked",
                        entity_type="user",
                        entity_id=str(user.id),
                    )
                )
            destination = "/google-complete?mode=link&google=linked"
        response = _return_to_app(settings, destination)
        _clear_state_cookie(response, settings)
        return response

    if existing_identity is not None:
        user = await users.get_by_id(existing_identity.user_id)
        if user is None or not user.is_active or not user.email_verified:
            destination = "/login?google=error"
        else:
            auth = AuthService(session, settings, mail)
            issued = await auth.issue_session_for_user(user, user_agent=agent, ip=ip)
            response = _return_to_app(settings, "/google-complete")
            _set_refresh_cookie(response, issued, settings)
            _clear_state_cookie(response, settings)
            return response
    else:
        existing_email = await users.get_by_email(claims.email)
        if existing_email is not None:
            destination = "/login?google=link-required"
        elif not settings.allow_registration:
            destination = "/login?google=registration-closed"
        elif not claims.google_controls_email:
            # Outside Gmail and Workspace, Google checked the address once and
            # no longer vouches for it: no account is created from it. The user
            # registers by email and links Google in settings (docs/auth.md).
            destination = "/login?google=email-unconfirmed"
        else:
            user = User(
                email=claims.email,
                password_hash=None,
                display_name=claims.name,
                role=UserRole.USER,
                is_active=True,
                email_verified=True,
            )
            await users.add(user)
            await identities.link_google(user, subject=claims.subject, email=claims.email)
            issued = await AuthService(session, settings, mail).issue_session_for_user(
                user, user_agent=agent, ip=ip
            )
            response = _return_to_app(settings, "/google-complete")
            _set_refresh_cookie(response, issued, settings)
            _clear_state_cookie(response, settings)
            await queue_new_user_notification(background, session, sender, user.email)
            return response

    response = _return_to_app(settings, destination)
    _clear_state_cookie(response, settings)
    return response
