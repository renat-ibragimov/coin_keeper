"""Merge default_grade_commemorative/default_grade_circulation into default_grade.

Owner's call (2026-09-13): the per-group split never paid for its complexity —
a collector still picks the actual grade per purchase, this only ever
pre-fills the purchase form's first suggestion, and one default for every new
purchase is simpler to reason about and to expose as an editable setting.
Every account's `default_grade_commemorative` has stayed at its column
default ('UNC') since no UI ever wrote to either column, so that value —
already the better of the two for a starting suggestion — backfills the
merged column.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("default_grade", sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE user_settings SET default_grade = default_grade_commemorative"))
    op.alter_column("user_settings", "default_grade", nullable=False, server_default="UNC")
    op.drop_column("user_settings", "default_grade_commemorative")
    op.drop_column("user_settings", "default_grade_circulation")


def downgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("default_grade_commemorative", sa.Text(), nullable=False, server_default="UNC"),
    )
    op.add_column(
        "user_settings",
        sa.Column("default_grade_circulation", sa.Text(), nullable=False, server_default="VF"),
    )
    op.execute(
        sa.text(
            "UPDATE user_settings SET "
            "default_grade_commemorative = default_grade, "
            "default_grade_circulation = default_grade"
        )
    )
    op.drop_column("user_settings", "default_grade")
