"""SMTP backend for the server (Resend or Postmark, docs/infra.md)."""

from __future__ import annotations

from email.message import Message as StdEmailMessage

import aiosmtplib

from app.core.config import Settings
from app.core.mail.base import EmailMessage, MailBackend


class SmtpMailBackend(MailBackend):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> None:
        payload = StdEmailMessage()
        payload["From"] = self._settings.smtp_from
        payload["To"] = message.to
        payload["Subject"] = message.subject
        payload.set_payload(message.body, charset="utf-8")

        # Failures propagate; the caller logs them once (AuthService._send_logged).
        await aiosmtplib.send(
            payload,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_user or None,
            password=self._settings.smtp_password or None,
            start_tls=self._settings.smtp_starttls,
        )
