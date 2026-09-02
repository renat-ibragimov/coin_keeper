"""Console backend: the message goes to the log, nothing leaves the process."""

from __future__ import annotations

import logging

from app.core.mail.base import EmailMessage, MailBackend

logger = logging.getLogger("app.mail")


class ConsoleMailBackend(MailBackend):
    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "outgoing email (console backend)\nTo: %s\nSubject: %s\n\n%s",
            message.to,
            message.subject,
            message.body,
        )
