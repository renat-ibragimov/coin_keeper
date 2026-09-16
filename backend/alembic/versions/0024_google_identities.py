"""Google sign-in identities and passwordless accounts.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("email_at_link", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("provider", "subject", name="uq_auth_identities_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_auth_identities_user_provider"),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])


def downgrade() -> None:
    has_passwordless = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE password_hash IS NULL)"))
        .scalar()
    )
    if has_passwordless:
        raise RuntimeError("Cannot downgrade while passwordless accounts exist")
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
