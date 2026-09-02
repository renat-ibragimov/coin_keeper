"""Mark price snapshots that failed validation.

The legacy database carries an unknown share of parser garbage (glued numbers,
years instead of prices, metal value instead of coin value). The migration
keeps every snapshot — the history is worth having — but flags the ones that
fail the checks in docs/05-integrations.md so they stay out of collection value
calculations. See docs/09-data-migration.md.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_price_snapshots",
        sa.Column("is_suspect", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Partial: suspect rows are the minority, and the queries that care about
    # them ask for exactly those.
    op.create_index(
        "ix_market_price_snapshots_suspect",
        "market_price_snapshots",
        ["catalog_item_id"],
        postgresql_where=sa.text("is_suspect"),
    )


def downgrade() -> None:
    op.drop_index("ix_market_price_snapshots_suspect", table_name="market_price_snapshots")
    op.drop_column("market_price_snapshots", "is_suspect")
