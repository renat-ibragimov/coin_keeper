"""include_supporting_expenses on user_settings.

Backs the "Враховувати супутні витрати у вартості колекції" toggle in
account settings (owner's call, 2026-09-22): whether delivery, a holder,
grading... count toward "Куплено загалом" and the value-change figure on the
coin card, or stay a separate informational line next to them. On by
default — most collectors already think of what they paid the courier as
part of what the coin cost them (docs/business-rules.md, BR-4).

Promoted from a browser-local (`localStorage`) prototype the same day it was
tried, per the rule that user preferences live on the server, not in localStorage.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column(
            "include_supporting_expenses", sa.Boolean(), nullable=False, server_default="true"
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "include_supporting_expenses")
