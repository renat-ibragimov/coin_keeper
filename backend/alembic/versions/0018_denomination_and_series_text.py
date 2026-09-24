"""Free-text denomination and series on a catalog item.

Owner's call (2026-09-14), from the "Додати" form: a coin of a country the
dictionaries say nothing about — an Austrian 5 euro, say — had nowhere to put
its face value or its series, and the two fields rendered as a disabled box
with an apology. Both now follow the split `composition_id`/`material`,
`edge_type_id`/`edge` and `quality_type_id`/`quality` already use
(docs/business-rules.md, rule 14): the dictionary row where one fits, the
collector's own words where none does.

`series_text` is deliberately *display only*. Series are shared records an
admin creates (rule 2), and completeness, the «Серії» screen and the series
filter are all counted on `series_id`; a typed-in name appears on the card and
in listings and takes part in none of that. The alternative — a personal
series row with a visibility filter of its own through the whole series layer
— is a feature in its own right, not a field on this form.

Both columns are plain nullable text, so this migration is additive and
reversible: nothing reads them until the code that writes them ships.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalog_items", sa.Column("denomination_text", sa.Text(), nullable=True))
    op.add_column("catalog_items", sa.Column("series_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_items", "series_text")
    op.drop_column("catalog_items", "denomination_text")
