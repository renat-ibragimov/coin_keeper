"""Country-level gate for the shared catalogue.

`countries.catalog_confirmed` marks a country whose catalogue is built out and
fit to browse as *the* catalogue. Unlike `is_active` it has no escape hatch:
`storefront_visible()` and `series_storefront_visible()`
(`app/repositories/catalog.py`, `app/repositories/series.py`) now require it
unconditionally, on top of their existing active/personal/owned checks —
a country a user has personal positions or instances in still never
surfaces in the shared catalogue until this flips (docs/04-business-rules.md,
§13a). The owner's own coins from such a country stay fully visible in their
collection; only the catalogue listings are gated.

Only Ukraine is confirmed today, matching the one country the catalogue
project has actually finished (docs/11-roadmap.md). Every other country,
including the ones the legacy migration seeded as shared (USA, USSR), starts
unconfirmed and stays out of catalogue listings until confirmed by hand.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.reference_data.countries import UKRAINE_CODE

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "countries",
        sa.Column("catalog_confirmed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute(
        sa.text("UPDATE countries SET catalog_confirmed = true WHERE code = :code").bindparams(
            code=UKRAINE_CODE
        )
    )


def downgrade() -> None:
    op.drop_column("countries", "catalog_confirmed")
