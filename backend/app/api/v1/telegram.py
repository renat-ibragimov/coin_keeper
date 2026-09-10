"""The bot's webhook: the one public endpoint nobody signs in to.

Telegram posts every update here. Three things keep it safe (docs/13-admin.md,
2.5): the secret in X-Telegram-Bot-Api-Secret-Token is checked before anything
is parsed, only `/start <code>` and `/last` are acted on at all, and the reply
is always 200 -- a non-200 makes telegram retry the same update for hours.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, Response, status

from app.api.deps import AppSettings, DbSession, Telegram
from app.services.telegram import TelegramUpdateService

router = APIRouter(prefix="/telegram", tags=["telegram"])
logger = logging.getLogger("app.telegram")


@router.post("/webhook")
async def telegram_webhook(
    session: DbSession,
    settings: AppSettings,
    sender: Telegram,
    update: dict[str, Any],
    secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> Response:
    if not settings.telegram_webhook_secret:
        # The bot is not configured on this server: behave as if the route
        # were not here at all.
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    if secret_token is None or not secrets.compare_digest(
        secret_token, settings.telegram_webhook_secret
    ):
        logger.warning("telegram webhook called without a valid secret token")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    await TelegramUpdateService(session, settings, sender).handle(update)
    return Response(status_code=status.HTTP_200_OK)
