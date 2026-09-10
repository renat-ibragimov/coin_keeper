"""The admin bot: linking a chat, answering it, and reporting into it.

Linking is the whole security model (docs/13-admin.md, 2.5). Anyone can find
the bot and press Start; what they cannot do is present a one-time code issued
to a signed-in administrator, and without one the update is ignored in
silence -- not refused, which would confirm the bot is alive.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import generate_token, hash_token
from app.core.telegram import TelegramMessage, TelegramSender
from app.core.telegram.messages import (
    job_run_message,
    link_confirmed_message,
    no_runs_message,
)
from app.models import User
from app.models.enums import AuthTokenKind, UserRole
from app.repositories.jobs import JobRunRepository
from app.repositories.telegram import TelegramRecipientRepository
from app.repositories.users import AuthTokenRepository, UserRepository

logger = logging.getLogger("app.telegram")

START_COMMAND = "/start"
LAST_COMMAND = "/last"


class BotNotConfiguredError(Exception):
    """No bot username to build a link with: 503."""


class TelegramLinkService:
    """Everything the admin section itself calls."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._tokens = AuthTokenRepository(session)
        self._recipients = TelegramRecipientRepository(session)

    async def create_link(self, user: User) -> tuple[str, datetime]:
        """A fresh code and the t.me link carrying it. Issuing a new code
        invalidates the previous one, as with every other one-time token."""
        if not self._settings.telegram_bot_username:
            raise BotNotConfiguredError
        raw = generate_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=self._settings.telegram_link_ttl_minutes)
        await self._tokens.issue(
            user_id=user.id,
            kind=AuthTokenKind.TELEGRAM_LINK,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
        username = self._settings.telegram_bot_username.lstrip("@")
        return f"https://t.me/{username}?start={raw}", expires_at

    async def list_chats(self, user: User) -> list[int]:
        return [chat.chat_id for chat in await self._recipients.list_for_user(user.id)]

    async def unlink(self, user: User) -> int:
        return await self._recipients.unlink_user(user.id)


class TelegramUpdateService:
    """The webhook side: what an incoming update is allowed to do."""

    def __init__(self, session: AsyncSession, settings: Settings, sender: TelegramSender) -> None:
        self._session = session
        self._settings = settings
        self._sender = sender
        self._tokens = AuthTokenRepository(session)
        self._recipients = TelegramRecipientRepository(session)
        self._users = UserRepository(session)

    async def handle(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        text = message.get("text")
        if not isinstance(chat, dict) or not isinstance(text, str):
            return
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return

        command, _, argument = text.strip().partition(" ")
        if command == START_COMMAND:
            await self._start(chat_id, argument.strip())
        elif command == LAST_COMMAND:
            await self._last(chat_id)
        # Anything else: no reply. The bot has no small talk, and answering
        # would tell a stranger it is listening.

    async def _start(self, chat_id: int, code: str) -> None:
        if not code:
            return
        record = await self._tokens.get_usable(
            token_hash=hash_token(code), kind=AuthTokenKind.TELEGRAM_LINK
        )
        if record is None:
            logger.info("telegram link attempt with an unusable code from chat %s", chat_id)
            return
        user = await self._users.get_by_id(record.user_id)
        if user is None or user.role != UserRole.ADMIN:
            # The role can have been taken away between issuing the code and
            # pressing Start.
            logger.info("telegram link code belonged to a non-admin, ignoring")
            return

        await self._tokens.mark_used(record)
        await self._recipients.link(user_id=user.id, chat_id=chat_id)
        await self._sender.send(TelegramMessage(chat_id=chat_id, text=link_confirmed_message()))

    async def _last(self, chat_id: int) -> None:
        if await self._recipients.get_by_chat(chat_id) is None:
            return
        runs, _ = await JobRunRepository(self._session).list_runs(job=None, limit=1, offset=0)
        if not runs:
            await self._sender.send(TelegramMessage(chat_id=chat_id, text=no_runs_message()))
            return
        await self._sender.send(
            TelegramMessage(
                chat_id=chat_id,
                text=job_run_message(runs[0], admin_url=admin_url(self._settings)),
            )
        )


def admin_url(settings: Settings) -> str | None:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/admin" if base else None


async def notify_job_run(sender: TelegramSender, chat_ids: list[int], text: str) -> None:
    """Fan a finished run out to every linked chat.

    Called after the response has gone back to the reporting job, so a slow
    or unreachable telegram never holds up a night's work.
    """
    for chat_id in chat_ids:
        await sender.send(TelegramMessage(chat_id=chat_id, text=text))
