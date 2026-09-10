"""Bot API backend: one POST to sendMessage, no library.

The bot only speaks outward here; incoming updates arrive through the webhook
(app/api/v1/telegram.py), so nothing in this module polls or keeps a session.
"""

from __future__ import annotations

import logging

import httpx

from app.core.telegram.base import TelegramMessage, TelegramSender

logger = logging.getLogger("app.telegram")

TIMEOUT_SECONDS = 10.0


class BotApiTelegramSender(TelegramSender):
    def __init__(self, token: str) -> None:
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"

    async def send(self, message: TelegramMessage) -> None:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self._url,
                    json={
                        "chat_id": message.chat_id,
                        "text": message.text,
                        "disable_web_page_preview": True,
                    },
                )
        except httpx.HTTPError as exc:
            # Swallowed on purpose: a report that could not be delivered is
            # still recorded in job_runs and visible in the admin section.
            logger.warning("telegram send failed for chat %s: %s", message.chat_id, exc)
            return
        if response.status_code != httpx.codes.OK:
            logger.warning(
                "telegram refused a message for chat %s: %s %s",
                message.chat_id,
                response.status_code,
                response.text[:200],
            )
