"""Wire types for the admin bot (docs/13-admin.md)."""

from __future__ import annotations

from datetime import datetime

from app.schemas.base import CamelModel


class TelegramLinkOut(CamelModel):
    """The t.me link carrying a one-time code, and when it stops working."""

    url: str
    expires_at: datetime


class TelegramStatusOut(CamelModel):
    """Whether this administrator has a chat connected. The chat id itself is
    not sent: the screen has no use for it."""

    connected: bool
    chats: int
