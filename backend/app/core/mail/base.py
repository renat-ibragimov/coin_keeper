"""Mail transport abstraction.

Two backends, chosen by MAIL_BACKEND (docs/10-infra.md): "console" writes the
whole message to the log so local development and tests need no secrets,
"smtp" actually sends. Everything above this layer is identical either way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class MailBackend(ABC):
    @abstractmethod
    async def send(self, message: EmailMessage) -> None: ...
