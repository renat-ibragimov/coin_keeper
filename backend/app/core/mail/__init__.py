"""Mail backends and message templates."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.mail.base import EmailMessage, MailBackend
from app.core.mail.console import ConsoleMailBackend
from app.core.mail.messages import password_reset_email, verification_email
from app.core.mail.smtp import SmtpMailBackend


def build_mail_backend(settings: Settings) -> MailBackend:
    if settings.mail_backend == "smtp":
        return SmtpMailBackend(settings)
    return ConsoleMailBackend()


@lru_cache
def get_mail_backend() -> MailBackend:
    return build_mail_backend(get_settings())


__all__ = [
    "ConsoleMailBackend",
    "EmailMessage",
    "MailBackend",
    "SmtpMailBackend",
    "build_mail_backend",
    "get_mail_backend",
    "password_reset_email",
    "verification_email",
]
