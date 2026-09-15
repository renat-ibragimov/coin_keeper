"""Flip user_settings.show_packaging_variants to on by default.

Owner's call (2026-09-12, same day as 0012): a souvenir-packaging card should
show alongside the bare coin unless the viewer opts out, not the other way
round — hiding by default made the catalog look incomplete for everyone who
never touched the setting. `GET /catalog` behaviour itself
(`CatalogRepository._filter_conditions`) is unchanged; only the default a
fresh `user_settings` row starts from flips, matching the account-settings
toggle now reading "on unless you turn it off". No account has knowingly
opted out yet (the toggle shipped in 0012 earlier the same day), so every
existing row is backfilled to `true` along with the new default — there is
no way to tell "never touched" apart from "explicitly turned off" once 0012
has run, and the feature has had no real usage window in between.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("user_settings", "show_packaging_variants", server_default="true")
    op.execute(sa.text("UPDATE user_settings SET show_packaging_variants = true"))


def downgrade() -> None:
    op.alter_column("user_settings", "show_packaging_variants", server_default="false")
    op.execute(sa.text("UPDATE user_settings SET show_packaging_variants = false"))
