"""Add secondary_currency to user_settings.

Owner's call (2026-09-13): the primary displayed amount stays UAH everywhere
— it is the ledger currency every purchase and expense already converts to
— but which "≈ …" conversion shows alongside it (USD or EUR) becomes a
per-user choice instead of being hardcoded to USD. NBU rate history only
covers USD and EUR, so those are the only two options.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("secondary_currency", sa.Text(), nullable=False, server_default="USD"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "secondary_currency")
