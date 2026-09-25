"""Refresh token families, revoke reasons and session metadata.

Reuse detection used to revoke every session of the user whenever a revoked
refresh token came back. Benign replays — a refresh response lost on a mobile
network, a reload while a refresh is in flight, two tabs — logged the owner out
of desktop and phone at once (12 times in three weeks on production). Rotation
now works per family: one family per sign-in, a short grace window for replays
of a just-rotated token, and a proven replay revokes that family only
(docs/auth.md, "Sessions"; RFC 9700, section 4.14.2).

- `family_id` / `parent_id`: the rotation chain of one sign-in.
- `revoke_reason`: only a replayed `rotated` token is evidence of theft; tokens
  ended by logout or a password change stay a plain 401.
- `session_started_at` / `persistent`: when the sign-in happened and whether it
  was "remember me". Stored now, used by the session-lifetime rules later.

Every existing token is revoked (`logout_all`): the old rows carry no chain, so
they are retired rather than guessed into families. Everyone signs in once
more (owner's call, 2026-09-25).

Downgrade drops the new columns. The forced sign-out is not undone.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Short name: the metadata naming convention adds the "ck_refresh_tokens_" prefix.
REVOKE_REASON_CHECK = "revoke_reason_valid"
PARENT_FK = "fk_refresh_tokens_parent_id"
FAMILY_INDEX = "ix_refresh_tokens_family_id"
ACTIVE_INDEX = "ix_refresh_tokens_user_id_active"


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("revoke_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        REVOKE_REASON_CHECK,
        "refresh_tokens",
        "revoke_reason IS NULL OR revoke_reason IN "
        "('rotated', 'logout', 'reuse', 'password_change', 'password_reset', 'logout_all')",
    )
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.add_column("refresh_tokens", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        PARENT_FK, "refresh_tokens", "refresh_tokens", ["parent_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "session_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("UPDATE refresh_tokens SET session_started_at = created_at")
    op.add_column(
        "refresh_tokens",
        sa.Column("persistent", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Retire every existing token: one forced sign-in for everyone.
    op.execute("UPDATE refresh_tokens SET revoked_at = now() WHERE revoked_at IS NULL")
    op.execute("UPDATE refresh_tokens SET revoke_reason = 'logout_all'")

    op.create_index(FAMILY_INDEX, "refresh_tokens", ["family_id"])
    op.create_index(
        ACTIVE_INDEX,
        "refresh_tokens",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(ACTIVE_INDEX, table_name="refresh_tokens")
    op.drop_index(FAMILY_INDEX, table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "persistent")
    op.drop_column("refresh_tokens", "session_started_at")
    op.drop_constraint(PARENT_FK, "refresh_tokens", type_="foreignkey")
    op.drop_column("refresh_tokens", "parent_id")
    op.drop_column("refresh_tokens", "family_id")
    op.drop_constraint(REVOKE_REASON_CHECK, "refresh_tokens", type_="check")
    op.drop_column("refresh_tokens", "revoke_reason")
