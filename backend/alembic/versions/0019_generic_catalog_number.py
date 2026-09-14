"""A catalog number that belongs to no particular catalogue.

`catalog_km`, `catalog_uc` and `catalog_numista` each name a specific
numbering system, and the pipeline fills them from the source that uses it.
A collector entering a coin by hand has one number and no reason to know
whose it is — the "Додати" form asked which of the three it was and got three
empty boxes for its trouble (owner's call, 2026-09-14).

`catalog_number` is that number, unattributed. It is last in the chain the
card and the listings already read (`catalog_km or catalog_uc or
catalog_numista or catalog_number`), so a named number still wins wherever
one exists, and the card's own "Каталожний номер" row — which until now only
ever showed a number that happened not to match any of the three — finally
has a column behind it.

Nothing is migrated into it: every existing row got its numbers from a source
that named the system, and guessing which system a hand-typed number belongs
to is exactly what this column exists to avoid.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalog_items", sa.Column("catalog_number", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_items", "catalog_number")
