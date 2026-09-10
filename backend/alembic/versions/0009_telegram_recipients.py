"""telegram_recipients and the link token kind.

The admin bot needs somewhere to keep the chats it may write to. They are not
configured by hand: an administrator presses a button in the admin section,
gets a one-time code and a t.me link, and pressing Start hands the code back
through the webhook (docs/13-admin.md, 2.5). Hence the third auth_tokens kind
-- the one-time machinery for email confirmation and password resets already
does exactly what a link code needs, hash and expiry included.

chat_id is UNIQUE: one chat belongs to one administrator, and linking a chat
that is already linked moves it rather than duplicating it.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Postgres 12+ allows this inside a transaction; what it still forbids is
    # *using* the new value in the same one, which this migration does not do.
    op.execute("ALTER TYPE auth_token_kind ADD VALUE IF NOT EXISTS 'telegram_link'")

    op.create_table(
        "telegram_recipients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_telegram_recipients_user_id", "telegram_recipients", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_telegram_recipients_user_id", table_name="telegram_recipients")
    op.drop_table("telegram_recipients")
    # The enum value stays: removing one requires rewriting the type, and an
    # unused label costs nothing.
