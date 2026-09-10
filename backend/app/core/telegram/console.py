"""Console backend: the message goes to the log, nothing leaves the process."""

from __future__ import annotations

import logging

from app.core.telegram.base import TelegramMessage, TelegramSender

logger = logging.getLogger("app.telegram")


class ConsoleTelegramSender(TelegramSender):
    async def send(self, message: TelegramMessage) -> None:
        logger.info(
            "outgoing telegram (console backend)\nChat: %s\n\n%s", message.chat_id, message.text
        )
