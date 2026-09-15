"""show_packaging_variants on user_settings.

Backs the "show souvenir-packaging coins as their own card" toggle in
account settings. Off by default: `GET /catalog` hides any
`catalog_items` row whose `packaging_of_id` (0011) points at another item
unless the viewing user has this set, per-user rather than global because
which cards feel like noise is a matter of taste (docs/04-business-rules.md).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("show_packaging_variants", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "show_packaging_variants")
