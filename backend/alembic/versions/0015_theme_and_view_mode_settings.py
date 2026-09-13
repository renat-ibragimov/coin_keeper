"""Add theme, catalog_view_mode, collection_view_mode to user_settings.

Owner's call (2026-09-13): theme and the cards/table view for catalog and
collection were browser-only (localStorage), so a new device or a cleared
browser lost them. Moving them into `user_settings` puts every cross-device
preference in one place, delivered by `GET /bootstrap` like `default_grade`
and `show_packaging_variants` already are. The client still keeps a
localStorage copy for instant paint before this row is fetched (and for the
signed-out screens, before there is a user at all) — this column is the
value that survives a new browser or device, not a replacement for that cache.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("theme", sa.Text(), nullable=False, server_default="system"),
    )
    op.add_column(
        "user_settings",
        sa.Column("catalog_view_mode", sa.Text(), nullable=False, server_default="cards"),
    )
    op.add_column(
        "user_settings",
        sa.Column("collection_view_mode", sa.Text(), nullable=False, server_default="cards"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "collection_view_mode")
    op.drop_column("user_settings", "catalog_view_mode")
    op.drop_column("user_settings", "theme")
