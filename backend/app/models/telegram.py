"""Who the admin bot talks to (docs/13-admin.md, 2.5)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column


class TelegramRecipient(Base):
    """A chat that receives admin notifications, and the admin it belongs to.

    A row can only appear through a one-time link code issued to a signed-in
    administrator, which is what keeps strangers out: anyone can find the bot
    and press Start, but without a code nothing happens (docs/13-admin.md).
    """

    __tablename__ = "telegram_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Telegram chat ids are 64-bit and negative for groups.
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    linked_at: Mapped[datetime] = created_at_column()

    __table_args__ = (Index("ix_telegram_recipients_user_id", "user_id"),)
