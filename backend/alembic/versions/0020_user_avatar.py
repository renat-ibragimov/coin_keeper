"""A profile picture for the account.

One nullable column holding a storage key, not a `media_files` row: that
table's CHECK constraint ties every file to a catalog or collection item, and
its source/role columns answer questions ("whose rights are these?", "obverse
or reverse?") that a face does not raise.

The key is `users/{id}/avatar/{sha256[:12]}_256.webp` — the digest of the
uploaded source, so replacing the picture lands on a new key and no cached URL
keeps serving the previous one. One size only: the interface shows an avatar at
26-40 css px, which 256 covers even on a 3x display.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_key")
