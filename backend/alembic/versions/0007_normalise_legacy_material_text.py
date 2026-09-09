"""Technical material tokens out of the catalogue's free-text material field.

Twenty-four shared records carry a token instead of an alloy name: either one
of our own dictionary codes ("nickel_silver") or a bare metal with no fineness
("silver", "gold"). They come from the owner's legacy base, and migration 0003
kept them the way it keeps every material string it cannot parse. Nothing read
the field until the catalogue listings started showing it, and now
"nickel_silver" is on a card.

A code names a dictionary row, so the row is what the record gets: the code
resolves to `composition_id` and the text goes away. A bare metal names no
row — the National Bank's cards give silver and gold no fineness, which is why
`materials` has no plain "silver" — so it stays text, in the same wording the
Ukrainian loader stores ("срібло", "золото") and eighty-five other records
already carry.

`app.reference_data.materials` learns both tokens at the same time, so a
re-run of the legacy import does not bring them back.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.reference_data.materials import BARE_METAL_WORDS

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A code that names a dictionary row: point the record at the row and drop the
# text. An item that already has a composition keeps it — the token is then
# only a leftover.
RESOLVE_CODES = sa.text("""
UPDATE catalog_items AS item
SET composition_id = COALESCE(item.composition_id, dictionary.id),
    material = NULL
FROM materials AS dictionary
WHERE dictionary.code = lower(btrim(item.material))
""")

# A bare metal: the text is all there is, so only its wording changes. Where a
# composition is already known the text says nothing the row does not.
REWORD_BARE_METAL = sa.text("""
UPDATE catalog_items
SET material = CASE WHEN composition_id IS NULL THEN :wording ELSE NULL END
WHERE lower(btrim(material)) = :token
""")


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(RESOLVE_CODES)
    for token, wording in BARE_METAL_WORDS.items():
        connection.execute(REWORD_BARE_METAL, {"token": token, "wording": wording})


def downgrade() -> None:
    """Nothing to undo.

    The tokens were a defect, not a state worth restoring, and which record
    held which one is not recoverable from the normalised data.
    """
