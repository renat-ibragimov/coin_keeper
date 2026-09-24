"""Who the admin bot talks to (docs/admin.md, "Linking a chat")."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column


class TelegramRecipient(Base):
    """A chat that receives admin notifications, and the admin it belongs to.

    A row can only appear through a one-time link code issued to a signed-in
    administrator, which is what keeps strangers out: anyone can find the bot
    and press Start, but without a code nothing happens (docs/admin.md).
    """

    __tablename__ = "telegram_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Telegram chat ids are 64-bit and negative for groups.
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    linked_at: Mapped[datetime] = created_at_column()

    __table_args__ = (Index("ix_telegram_recipients_user_id", "user_id"),)


class SupportTelegramSettings(Base):
    __tablename__ = "support_telegram_settings"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    configured_at: Mapped[datetime] = created_at_column()
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)


class SupportLinkToken(Base):
    __tablename__ = "support_link_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="uk", server_default="uk")
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()
    __table_args__ = (Index("ix_support_link_tokens_user_id", "user_id"),)


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(Text)
    telegram_name: Mapped[str | None] = mapped_column(Text)
    admin_topic_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    source_path: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="uk", server_default="uk")
    created_at: Mapped[datetime] = created_at_column()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="status"),
        Index("ix_support_tickets_telegram_chat_id_status", "telegram_chat_id", "status"),
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="text", server_default="text")
    text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    __table_args__ = (
        CheckConstraint("direction IN ('user_to_admin', 'admin_to_user')", name="direction"),
    )
