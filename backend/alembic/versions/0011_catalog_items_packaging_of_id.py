"""Self-referencing packaging_of_id on catalog_items.

coin-parser can now detect when a "souvenir packaging" catalogue card
(NBU's own "у сувенірній упаковці"/"у сувенірному пакованні" suffix) is the
same physical coin as a bare card in the same (series, title without the
packaging suffix, issue year) group -- matched on exact weight_grams and
diameter_mm, mintage deliberately excluded (docs/01_findings.md in
coin-parser). It writes `card["packaging_of"] = <bare source_id>` into
cards.json on every parse and resolves that into a real catalog_items.id in
`load_cards.py`'s second pass, but that pass needs somewhere to put the
result.

This migration only adds that column and its index. Nothing reads or writes
it yet beyond the loader -- no API field, no frontend toggle. The eventual
per-user "show souvenir packaging separately" setting (off by default) is a
separate task; this column is self-referencing rather than a join table
specifically so that future toggle can walk straight from a bare item to its
packaging variant.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_items",
        sa.Column(
            "packaging_of_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="SET NULL",
                name="fk_catalog_items_packaging_of_id",
            ),
        ),
    )
    op.create_index(
        "ix_catalog_items_packaging_of_id",
        "catalog_items",
        ["packaging_of_id"],
        postgresql_where=sa.text("NOT is_archived"),
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_items_packaging_of_id", table_name="catalog_items")
    op.drop_column("catalog_items", "packaging_of_id")
