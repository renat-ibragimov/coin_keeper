"""Telegram support inbox: site links and the two-way relay."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import generate_token, hash_token
from app.core.support_telegram import SupportTelegramClient
from app.models import SupportLinkToken, SupportTicket, User
from app.repositories.support import SupportRepository


class SupportNotConfiguredError(Exception):
    pass


class SupportService:
    def __init__(
        self, session: AsyncSession, settings: Settings, telegram: SupportTelegramClient
    ) -> None:
        self.session = session
        self.settings = settings
        self.telegram = telegram
        self.repo = SupportRepository(session)

    def public_url(self) -> str:
        username = self.settings.support_telegram_bot_username.lstrip("@")
        if not username:
            raise SupportNotConfiguredError
        return f"https://t.me/{username}"

    async def linked_url(self, user: User, source_path: str | None) -> str:
        if not self.settings.support_telegram_bot_token:
            raise SupportNotConfiguredError
        raw = generate_token()
        await self.repo.issue_link(
            SupportLinkToken(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=self.settings.support_telegram_link_ttl_minutes),
                source_path=(source_path or "")[:500] or None,
                locale=user.locale,
            )
        )
        return f"{self.public_url()}?start={raw}"

    async def handle(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            await self._callback(callback)
            return
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        sender = message.get("from")
        if (
            not isinstance(chat, dict)
            or not isinstance(sender, dict)
            or sender.get("is_bot") is not False
        ):
            return
        chat_id = chat.get("id")
        if type(chat_id) is not int:
            return
        if chat.get("type") == "private" and sender.get("id") == chat_id:
            await self._user_message(message, chat, sender)
        elif chat.get("type") == "supergroup":
            await self._group_message(message, chat_id)

    async def _user_message(
        self, message: dict[str, Any], chat: dict[str, Any], sender: dict[str, Any]
    ) -> None:
        chat_id = int(chat["id"])
        text = message.get("text")
        if isinstance(text, str) and text.startswith("/start"):
            _, _, code = text.partition(" ")
            token = await self.repo.consume_link(hash_token(code.strip())) if code.strip() else None
            ticket = await self.repo.open_ticket_for_chat(chat_id)
            if ticket is None and token is not None:
                ticket = await self._new_ticket(chat_id, sender, token=token)
            elif ticket is not None and token is not None:
                ticket.user_id = token.user_id
                ticket.source_path = token.source_path
                ticket.locale = token.locale
                await self.session.flush()
            locale = ticket.locale if ticket else "uk"
            await self.telegram.send_message(chat_id, self._welcome(locale))
            return

        ticket = await self.repo.open_ticket_for_chat(chat_id)
        if ticket is None:
            ticket = await self._new_ticket(chat_id, sender)
        if ticket is None or ticket.admin_topic_id is None:
            await self.telegram.send_message(
                chat_id, "Служба підтримки тимчасово недоступна. Спробуйте пізніше."
            )
            return
        message_id = message.get("message_id")
        if type(message_id) is not int:
            return
        copied_id = await self.telegram.copy_message(
            from_chat_id=chat_id,
            message_id=message_id,
            chat_id=(await self.repo.settings()).group_chat_id,  # type: ignore[union-attr]
            thread_id=ticket.admin_topic_id,
        )
        if copied_id is not None:
            await self.repo.add_message(
                ticket_id=ticket.id,
                direction="user_to_admin",
                telegram_message_id=message_id,
                kind=self._kind(message),
                text=self._text(message),
            )
            await self.telegram.send_message(chat_id, self._received(ticket.locale))

    async def _new_ticket(
        self, chat_id: int, sender: dict[str, Any], token: SupportLinkToken | None = None
    ) -> SupportTicket | None:
        configured = await self.repo.settings()
        if configured is None:
            return None
        # A site deep link proves the account once. Keep that association for
        # later tickets opened directly in Telegram; otherwise Telegram's own
        # language_code (often "en" even for a Ukrainian-speaking user) would
        # also replace the locale after every closed conversation.
        previous_linked = (
            await self.repo.latest_ticket_for_chat(chat_id, linked_only=True)
            if token is None
            else None
        )
        previous = previous_linked or (
            await self.repo.latest_ticket_for_chat(chat_id) if token is None else None
        )
        full_name = (
            " ".join(
                part
                for part in (sender.get("first_name"), sender.get("last_name"))
                if isinstance(part, str)
            ).strip()
            or None
        )
        ticket = await self.repo.create_ticket(
            user_id=token.user_id if token else (previous.user_id if previous else None),
            telegram_chat_id=chat_id,
            telegram_username=sender.get("username")
            if isinstance(sender.get("username"), str)
            else None,
            telegram_name=full_name,
            source_path=token.source_path if token else None,
            locale=(
                token.locale
                if token
                else (previous.locale if previous else (sender.get("language_code") or "uk")[:2])
            ),
        )
        user = await self.session.get(User, ticket.user_id) if ticket.user_id else None
        label = (
            user.display_name if user and user.display_name else full_name or f"Telegram {chat_id}"
        )
        topic_id = await self.telegram.create_topic(
            configured.group_chat_id, f"#{ticket.id} · {label}"
        )
        if topic_id is None:
            return None
        ticket.admin_topic_id = topic_id
        identity = [f"Звернення #{ticket.id}"]
        if user:
            identity.extend(
                [
                    f"Акаунт: {user.display_name or '—'}",
                    f"Email: {user.email}",
                    f"User ID: {user.id}",
                ]
            )
        identity.append(
            f"Telegram: @{ticket.telegram_username}"
            if ticket.telegram_username
            else f"Telegram ID: {chat_id}"
        )
        if ticket.source_path:
            identity.append(f"Сторінка: {ticket.source_path}")
        await self.telegram.send_message(
            configured.group_chat_id,
            "\n".join(identity),
            thread_id=topic_id,
            close_ticket_id=ticket.id,
        )
        return ticket

    async def _group_message(self, message: dict[str, Any], chat_id: int) -> None:
        configured = await self.repo.settings()
        if configured is None or configured.group_chat_id != chat_id:
            text = message.get("text")
            if isinstance(text, str) and text.startswith("/setup "):
                supplied = text.partition(" ")[2].strip()
                if (
                    self.settings.support_telegram_setup_secret
                    and secrets.compare_digest(
                        supplied, self.settings.support_telegram_setup_secret
                    )
                    and message.get("chat", {}).get("is_forum") is True
                ):
                    await self.repo.configure_group(chat_id)
                    await self.telegram.send_message(
                        chat_id, "Готово: ця група підключена до підтримки."
                    )
            return
        topic_id = message.get("message_thread_id")
        message_id = message.get("message_id")
        if (
            type(topic_id) is not int
            or type(message_id) is not int
            or message.get("forum_topic_created")
        ):
            return
        ticket = await self.repo.ticket_by_topic(topic_id)
        if ticket is None or ticket.status != "open":
            return
        copied_id = await self.telegram.copy_message(
            from_chat_id=chat_id, message_id=message_id, chat_id=ticket.telegram_chat_id
        )
        if copied_id is not None:
            await self.repo.add_message(
                ticket_id=ticket.id,
                direction="admin_to_user",
                telegram_message_id=message_id,
                kind=self._kind(message),
                text=self._text(message),
            )

    async def _callback(self, callback: dict[str, Any]) -> None:
        data = callback.get("data")
        callback_id = callback.get("id")
        message = callback.get("message")
        if (
            not isinstance(data, str)
            or not data.startswith("support:close:")
            or not isinstance(message, dict)
        ):
            return
        try:
            ticket_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        configured = await self.repo.settings()
        chat = message.get("chat")
        if (
            configured is None
            or not isinstance(chat, dict)
            or chat.get("id") != configured.group_chat_id
        ):
            return
        ticket = await self.repo.ticket_by_id(ticket_id)
        topic_id = ticket.admin_topic_id if ticket is not None else None
        if (
            ticket is None
            or ticket.status != "open"
            or topic_id is None
            or topic_id != message.get("message_thread_id")
        ):
            return
        await self.repo.close(ticket)
        await self.telegram.send_message(ticket.telegram_chat_id, self._closed(ticket.locale))
        await self.telegram.close_topic(configured.group_chat_id, topic_id)
        if isinstance(callback_id, str):
            await self.telegram.answer_callback(callback_id, "Звернення закрито")

    @staticmethod
    def _kind(message: dict[str, Any]) -> str:
        return next(
            (
                key
                for key in ("text", "photo", "document", "video", "voice", "audio", "sticker")
                if key in message
            ),
            "other",
        )

    @staticmethod
    def _text(message: dict[str, Any]) -> str | None:
        value = message.get("text") or message.get("caption")
        return value[:10000] if isinstance(value, str) else None

    @staticmethod
    def _welcome(locale: str) -> str:
        return (
            "Describe your question in one message. You can attach a photo."
            if locale == "en"
            else "Опишіть питання одним повідомленням. Можна додати фото."
        )

    @staticmethod
    def _received(locale: str) -> str:
        return (
            "Received. Support will reply here."
            if locale == "en"
            else "Отримали. Підтримка відповість у цьому чаті."  # noqa: RUF001
        )

    @staticmethod
    def _closed(locale: str) -> str:
        return (
            "The request has been closed. Send a new message if you need more help."
            if locale == "en"
            else "Звернення закрито. Надішліть нове повідомлення, якщо потрібна допомога."
        )
