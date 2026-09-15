"""Persistence for Telegram support conversations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportLinkToken, SupportMessage, SupportTelegramSettings, SupportTicket


class SupportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def configure_group(self, chat_id: int) -> None:
        settings = await self.settings()
        if settings is None:
            self.session.add(SupportTelegramSettings(id=1, group_chat_id=chat_id))
        else:
            settings.group_chat_id = chat_id
            settings.configured_at = datetime.now(UTC)
        await self.session.flush()

    async def settings(self) -> SupportTelegramSettings | None:
        return await self.session.get(SupportTelegramSettings, 1)

    async def issue_link(self, token: SupportLinkToken) -> None:
        await self.session.execute(
            update(SupportLinkToken)
            .where(SupportLinkToken.user_id == token.user_id, SupportLinkToken.used_at.is_(None))
            .values(used_at=datetime.now(UTC))
        )
        self.session.add(token)
        await self.session.flush()

    async def consume_link(self, token_hash: str) -> SupportLinkToken | None:
        result = await self.session.execute(
            select(SupportLinkToken)
            .where(
                SupportLinkToken.token_hash == token_hash,
                SupportLinkToken.used_at.is_(None),
                SupportLinkToken.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        token = result.scalar_one_or_none()
        if token is not None:
            token.used_at = datetime.now(UTC)
            await self.session.flush()
        return token

    async def open_ticket_for_chat(self, chat_id: int) -> SupportTicket | None:
        result = await self.session.execute(
            select(SupportTicket)
            .where(SupportTicket.telegram_chat_id == chat_id, SupportTicket.status == "open")
            .order_by(SupportTicket.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_ticket_for_chat(
        self, chat_id: int, *, linked_only: bool = False
    ) -> SupportTicket | None:
        query = select(SupportTicket).where(SupportTicket.telegram_chat_id == chat_id)
        if linked_only:
            query = query.where(SupportTicket.user_id.is_not(None))
        result = await self.session.execute(query.order_by(SupportTicket.id.desc()).limit(1))
        return result.scalar_one_or_none()

    async def ticket_by_topic(self, topic_id: int) -> SupportTicket | None:
        result = await self.session.execute(
            select(SupportTicket).where(SupportTicket.admin_topic_id == topic_id)
        )
        return result.scalar_one_or_none()

    async def ticket_by_id(self, ticket_id: int) -> SupportTicket | None:
        return await self.session.get(SupportTicket, ticket_id)

    async def create_ticket(self, **values: object) -> SupportTicket:
        ticket = SupportTicket(**values)
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def add_message(self, **values: object) -> None:
        self.session.add(SupportMessage(**values))
        await self.session.flush()

    async def close(self, ticket: SupportTicket) -> None:
        ticket.status = "closed"
        ticket.closed_at = datetime.now(UTC)
        await self.session.flush()
