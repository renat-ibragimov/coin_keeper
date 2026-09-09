"""Catalog status, quality, edited fields; official series; price key without NULL holes.

Four column additions and one constraint rebuild.

`coin_series.is_official` marks a series the issuer's own catalogue parser
maintains. No backfill: load-series flips it for the NBU series it walks, and
curated series and other countries stay false, which is the correct reading of
"official" here.

`catalog_items.status` gives an imported record somewhere to sit before it is
published. Existing rows become 'active' through the server default, and
nothing reads the column yet -- filtering drafts out of the catalogue belongs
to the admin stage, and until then only 'active' is ever written.

`catalog_items.edited_fields` lists the field names a human has corrected, so a
catalogue loader can leave them alone. Nobody writes it yet; the contract is
the point of adding it now.

`catalog_items.quality` holds the strike quality as a canonical code ('proof',
'special_uncirculated', 'uncirculated', 'brilliant_uncirculated', ...). The
schema had no home for it, while ua-coins keeps such coins as separate rows,
so the distinction was being dropped. No CHECK: the code dictionary lives in
coin-parser and will grow.

The price snapshot key is rebuilt as UNIQUE NULLS NOT DISTINCT. With the
default NULLS DISTINCT two snapshots that differ in nothing but a NULL grade do
not collide, so the history was protected from duplicates by loader discipline
alone. Rows that would violate the tighter key are collapsed to the lowest id
first, otherwise the constraint cannot be created.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out rather than left to the naming convention, which alembic
# operations do not carry.
STATUS_CHECK = "ck_catalog_items_status_valid"
PRICE_KEY = "uq_market_price_snapshots_item_source_grade_observed"
PRICE_KEY_COLUMNS = ("catalog_item_id", "source", "grade", "observed_at")

# Only NULL grades can be duplicates today: any group with a grade is already
# covered by the old constraint.
DEDUPLICATE_NULL_GRADES = """
DELETE FROM market_price_snapshots AS duplicate
USING market_price_snapshots AS kept
WHERE duplicate.grade IS NULL
  AND kept.grade IS NULL
  AND duplicate.catalog_item_id = kept.catalog_item_id
  AND duplicate.source = kept.source
  AND duplicate.observed_at = kept.observed_at
  AND duplicate.id > kept.id
"""


def upgrade() -> None:
    op.add_column(
        "coin_series",
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "catalog_items",
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    )
    op.create_check_constraint(
        STATUS_CHECK,
        "catalog_items",
        "status IN ('draft', 'active', 'rejected')",
    )
    op.add_column("catalog_items", sa.Column("edited_fields", postgresql.JSONB(), nullable=True))
    op.add_column("catalog_items", sa.Column("quality", sa.Text(), nullable=True))

    op.execute(DEDUPLICATE_NULL_GRADES)
    op.drop_constraint(PRICE_KEY, "market_price_snapshots", type_="unique")
    op.create_unique_constraint(
        PRICE_KEY,
        "market_price_snapshots",
        list(PRICE_KEY_COLUMNS),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_constraint(PRICE_KEY, "market_price_snapshots", type_="unique")
    op.create_unique_constraint(PRICE_KEY, "market_price_snapshots", list(PRICE_KEY_COLUMNS))

    op.drop_column("catalog_items", "quality")
    op.drop_column("catalog_items", "edited_fields")
    op.drop_constraint(STATUS_CHECK, "catalog_items", type_="check")
    op.drop_column("catalog_items", "status")
    op.drop_column("coin_series", "is_official")
