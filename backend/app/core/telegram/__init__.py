"""Admin bot: outgoing messages and their wording."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.telegram.api import BotApiTelegramSender
from app.core.telegram.base import TelegramMessage, TelegramSender
from app.core.telegram.console import ConsoleTelegramSender


def build_telegram_sender(settings: Settings) -> TelegramSender:
    if settings.telegram_bot_token:
        return BotApiTelegramSender(settings.telegram_bot_token)
    return ConsoleTelegramSender()


@lru_cache
def get_telegram_sender() -> TelegramSender:
    return build_telegram_sender(get_settings())


__all__ = [
    "BotApiTelegramSender",
    "ConsoleTelegramSender",
    "TelegramMessage",
    "TelegramSender",
    "build_telegram_sender",
    "get_telegram_sender",
]
