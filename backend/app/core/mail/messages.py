"""Email bodies.

English only for now; Ukrainian copy arrives with the frontend localisation in
stage 4 (docs/11-roadmap.md).
"""

from __future__ import annotations

from app.core.mail.base import EmailMessage


def verification_email(to: str, verify_url: str, ttl_hours: int) -> EmailMessage:
    body = (
        "Welcome to CoinKeeper.\n\n"
        "Confirm this address to activate your account:\n\n"
        f"{verify_url}\n\n"
        f"The link is valid for {ttl_hours} hours and can be used once.\n"
        "If you did not create an account, ignore this message.\n"
    )
    return EmailMessage(to=to, subject="Confirm your CoinKeeper account", body=body)


def password_reset_email(to: str, reset_url: str, ttl_hours: int) -> EmailMessage:
    body = (
        "Someone asked to reset the password for this CoinKeeper account.\n\n"
        "Set a new password here:\n\n"
        f"{reset_url}\n\n"
        f"The link is valid for {ttl_hours} hour(s) and can be used once.\n"
        "If this was not you, ignore this message: the password stays unchanged.\n"
    )
    return EmailMessage(to=to, subject="Reset your CoinKeeper password", body=body)
