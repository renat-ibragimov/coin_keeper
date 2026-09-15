"""Telegram support tickets, account links and group setup.

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_telegram_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            "configured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("id = 1", name="singleton"),
    )
    op.create_table(
        "support_link_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_path", sa.Text()),
        sa.Column("locale", sa.Text(), nullable=False, server_default="uk"),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_support_link_tokens_user_id", "support_link_tokens", ["user_id"])
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.Text()),
        sa.Column("telegram_name", sa.Text()),
        sa.Column("admin_topic_id", sa.BigInteger(), unique=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("source_path", sa.Text()),
        sa.Column("locale", sa.Text(), nullable=False, server_default="uk"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('open', 'closed')", name="status"),
    )
    op.create_index(
        "ix_support_tickets_telegram_chat_id_status",
        "support_tickets",
        ["telegram_chat_id", "status"],
    )
    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="text"),
        sa.Column("text", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("direction IN ('user_to_admin', 'admin_to_user')", name="direction"),
    )
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])


def downgrade() -> None:
    op.drop_table("support_messages")
    op.drop_table("support_tickets")
    op.drop_table("support_link_tokens")
    op.drop_table("support_telegram_settings")
