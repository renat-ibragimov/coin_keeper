"""Reads and writes over telegram_recipients (docs/13-admin.md)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram import TelegramRecipient


class TelegramRecipientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def link(self, *, user_id: int, chat_id: int) -> TelegramRecipient:
        """Linking a chat that is already linked moves it to this user rather
        than failing on the unique key: the chat belongs to whoever proved
        ownership last, with a valid code."""
        existing = await self.get_by_chat(chat_id)
        if existing is not None:
            existing.user_id = user_id
            await self._session.flush()
            return existing
        recipient = TelegramRecipient(user_id=user_id, chat_id=chat_id)
        self._session.add(recipient)
        await self._session.flush()
        return recipient

    async def get_by_chat(self, chat_id: int) -> TelegramRecipient | None:
        result = await self._session.execute(
            select(TelegramRecipient).where(TelegramRecipient.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[TelegramRecipient]:
        result = await self._session.execute(
            select(TelegramRecipient)
            .where(TelegramRecipient.user_id == user_id)
            .order_by(TelegramRecipient.id)
        )
        return list(result.scalars().all())

    async def all_chat_ids(self) -> list[int]:
        result = await self._session.execute(
            select(TelegramRecipient.chat_id).order_by(TelegramRecipient.id)
        )
        return list(result.scalars().all())

    async def unlink_user(self, user_id: int) -> int:
        """Returns how many chats were disconnected."""
        chats = await self.list_for_user(user_id)
        if chats:
            await self._session.execute(
                delete(TelegramRecipient).where(TelegramRecipient.user_id == user_id)
            )
        return len(chats)
