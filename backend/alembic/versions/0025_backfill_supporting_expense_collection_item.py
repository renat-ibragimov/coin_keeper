"""Backfill collection_item_id on pre-existing supporting expenses.

Owner's call (2026-09-22): supporting expenses (delivery, holder, grading...)
now carry `collection_item_id`, same as `coin_purchase`, so a repeat purchase
of the same catalog item does not mix up which delivery belongs to which
purchase (docs/04-business-rules.md, rule 4). No schema change — the column
has existed since the `expenses` table itself (`02-data-model.md`); this only
fills it in for rows written before the rule changed.

Only unambiguous rows are touched: a supporting expense whose
`(owner_id, catalog_item_id)` matches **exactly one** `collection_items` row
gets that row's id. A pair matching more than one purchase is left `NULL` —
there is no way to tell which purchase it belongs to, and guessing would be
worse than the status quo (still correctly summed at the item level via
`catalog_item_id`, just not attributable to one purchase). See the
"Backfilling existing rows" note in the same rule.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            WITH unambiguous AS (
                SELECT owner_id, catalog_item_id, MIN(id) AS collection_item_id
                FROM collection_items
                GROUP BY owner_id, catalog_item_id
                HAVING COUNT(*) = 1
            )
            UPDATE expenses e
            SET collection_item_id = u.collection_item_id
            FROM unambiguous u
            WHERE e.category <> 'coin_purchase'
              AND e.collection_item_id IS NULL
              AND e.catalog_item_id = u.catalog_item_id
              AND e.owner_id = u.owner_id
            """
        )
    )


def downgrade() -> None:
    # Deliberately a no-op: this migration only fills in a link that was
    # already NULL, on rows a human is free to have corrected by hand since.
    # Blindly re-nulling every non-coin_purchase collection_item_id would
    # also undo links the service has set on purchases made after this
    # migration ran, which this migration never touched in the first place.
    pass
