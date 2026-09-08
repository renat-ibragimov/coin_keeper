"""Add descriptions and artists jsonb columns to catalog_items.

Both columns are filled by the coin-collector parser, never by hand. Rows
untouched by the parser keep NULL; no backfill runs here, so no
server_default.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalog_items", sa.Column("descriptions", postgresql.JSONB(), nullable=True))
    op.add_column("catalog_items", sa.Column("artists", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_items", "artists")
    op.drop_column("catalog_items", "descriptions")
