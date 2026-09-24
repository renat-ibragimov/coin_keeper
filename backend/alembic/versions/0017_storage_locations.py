"""Storage locations: a per-user dictionary plus a default setting.

Owner's call (2026-09-13): "Місце зберігання" gets its own dictionary table
instead of free text, so it can be bilingual (a collector's own custom entry
gets translated in the background, docs/business-rules.md) and reused
across purchases instead of drifting into a dozen near-duplicate spellings.
A single system preset (`owner_id IS NULL`, "Вдома") ships with the
migration — it fits almost everyone and stays undeletable; anything else,
"В дорозі" included, is created the first time an owner types it.

`collection_items.storage_location` was added in an earlier migration but
never wired into the API or the UI — confirmed empty for every real account
(2026-09-13 read of production), so it is dropped outright rather than
migrated. `user_settings.default_storage_location_id` pre-fills the purchase
form the same way `default_grade` already does.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name_uk, name_en) — a single preset, deliberately: it should fit almost
# everyone without crowding the dropdown (owner's brief); anything more
# specific is for the owner to add themselves.
_PRESETS = [
    ("Вдома", "At home"),
]


def upgrade() -> None:
    op.create_table(
        "storage_locations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name_original", sa.Text(), nullable=False),
        sa.Column("name_uk", sa.Text(), nullable=False),
        sa.Column(
            "name_uk_source",
            postgresql.ENUM(name="translation_source", create_type=False),
            nullable=False,
        ),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column(
            "name_en_source",
            postgresql.ENUM(name="translation_source", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    translation_source = postgresql.ENUM(name="translation_source", create_type=False)
    locations = sa.table(
        "storage_locations",
        sa.column("name_original", sa.Text()),
        sa.column("name_uk", sa.Text()),
        sa.column("name_uk_source", translation_source),
        sa.column("name_en", sa.Text()),
        sa.column("name_en_source", translation_source),
    )
    op.bulk_insert(
        locations,
        [
            {
                "name_original": name_uk,
                "name_uk": name_uk,
                "name_uk_source": "manual",
                "name_en": name_en,
                "name_en_source": "manual",
            }
            for name_uk, name_en in _PRESETS
        ],
    )

    op.add_column(
        "collection_items",
        sa.Column(
            "storage_location_id",
            sa.BigInteger(),
            sa.ForeignKey("storage_locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_column("collection_items", "storage_location")

    op.add_column(
        "user_settings",
        sa.Column(
            "default_storage_location_id",
            sa.BigInteger(),
            sa.ForeignKey("storage_locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "default_storage_location_id")
    op.add_column("collection_items", sa.Column("storage_location", sa.Text(), nullable=True))
    op.drop_column("collection_items", "storage_location_id")
    op.drop_table("storage_locations")
