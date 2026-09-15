"""Site links and webhook for the public support bot."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Header, Response, status

from app.api.deps import AppSettings, CurrentUser, DbSession, SupportTelegram
from app.api.errors import ProblemError
from app.schemas.support import SupportLinkIn, SupportLinkOut
from app.services.support import SupportNotConfiguredError, SupportService

router = APIRouter(prefix="/support", tags=["support"])


def unavailable() -> ProblemError:
    return ProblemError(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "support-not-configured",
        "Service unavailable",
        "Telegram support is not configured.",
    )


@router.get("/telegram")
async def public_support_link(
    settings: AppSettings, session: DbSession, telegram: SupportTelegram
) -> SupportLinkOut:
    try:
        return SupportLinkOut(url=SupportService(session, settings, telegram).public_url())
    except SupportNotConfiguredError as exc:
        raise unavailable() from exc


@router.post("/telegram/link")
async def linked_support_link(
    body: SupportLinkIn,
    user: CurrentUser,
    settings: AppSettings,
    session: DbSession,
    telegram: SupportTelegram,
) -> SupportLinkOut:
    try:
        url = await SupportService(session, settings, telegram).linked_url(user, body.source_path)
    except SupportNotConfiguredError as exc:
        raise unavailable() from exc
    return SupportLinkOut(url=url)


@router.post("/telegram/webhook")
async def support_webhook(
    update: dict[str, Any],
    session: DbSession,
    settings: AppSettings,
    telegram: SupportTelegram,
    secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> Response:
    expected = settings.support_telegram_webhook_secret
    if not settings.support_telegram_bot_token or not expected:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    if secret_token is None or not secrets.compare_digest(secret_token, expected):
        return Response(status_code=status.HTTP_403_FORBIDDEN)
    await SupportService(session, settings, telegram).handle(update)
    return Response(status_code=status.HTTP_200_OK)
