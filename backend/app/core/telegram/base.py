"""Telegram transport abstraction.

Two backends, chosen by whether a bot token is configured (docs/10-infra.md):
without one, messages go to the log, so local development and tests need no
secret and can never reach a real chat. Everything above this layer is the
same either way -- the mail module works on the same principle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    chat_id: int
    text: str


class TelegramSender(ABC):
    @abstractmethod
    async def send(self, message: TelegramMessage) -> None:
        """Deliver one message. Never raises: a chat that cannot be reached
        must not fail whatever the caller was really doing."""
