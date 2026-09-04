"""Record which sizes of an image are stored.

An image is kept at 300, 600 and 1200 px (docs/06-media-storage.md): a listing,
a card and the lightbox each want a different one, and one file for all three
either wastes bandwidth or blurs the lightbox. `storage_key` and
`thumbnail_key` can name two of them, not three, so the set of keys goes into
one column and those two stay as the largest and the preview.

Rows written before this migration keep their two keys and no variants; the URL
builder falls back to them, so nothing has to be re-uploaded.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_files", sa.Column("variants", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("media_files", "variants")
