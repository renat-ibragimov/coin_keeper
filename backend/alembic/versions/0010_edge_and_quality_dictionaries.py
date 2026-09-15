"""Edge and quality dictionaries; material fineness dropped.

Two new tables, `edge_types` and `quality_types`, mirror `materials` exactly
(code + name_uk + name_en, no `name_original` -- edge and strike quality are
universal numismatic vocabulary, not something an issuer names in its own
language, docs/04-business-rules.md, rule 14). `catalog_items` gets an
`edge_type_id` and a `quality_type_id` FK alongside the `edge`/`quality` text
columns it already had, the same split `composition_id`/`material` already
uses: a dictionary row where one is known, the source's own text where it is
not.

`quality_types` gives a home to data that was already there: some earlier,
uncommitted script filled `catalog_items.quality` for 1132 rows and nothing
has read the column since (docs/04-business-rules.md, rule 14). This migration
does not write `quality` itself, only the dictionary and the FK -- the
backfill below resolves whatever the column already holds.

Materials lose their fineness. The National Bank's own "Матеріал" filter
never states one for silver or gold (`NBU_METALS`,
app/ukraine_pipeline/sources.py), so a "Срібло 925" the legacy collection
carried was never something our only source of truth actually said. Existing
`silver_*`/`gold_*`/`silver_gilded_*` rows collapse into one row per family;
catalog_items pointing at a collapsed row are repointed first. A fresh
database never has the old rows at all -- migration 0003 seeds the collapsed
dictionary directly -- so this step is a no-op there and only does real work
against a database migrated before 2026-09-12.

The backfill resolves `material`/`edge`/`quality` text left over from before
each dictionary existed (or, for materials, before it covered every category
NBU's site actually offers) into the matching FK, clearing the text once a
row is found for it -- the same rule migration 0007 already applies to
`material`. Aliases cover raw tokens that do not already spell a dictionary
code (`app/reference_data/materials.py` `LEGACY_RAW_ALIASES`).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.reference_data.edge_types import EDGE_TYPES
from app.reference_data.quality_types import QUALITY_TYPES

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Family name -> (old codes to collapse, the survivor's new code/uk/en).
# Only the survivor keeps a row; the rest are deleted once repointed.
MATERIAL_CONSOLIDATIONS: tuple[tuple[str, tuple[str, ...], str, str, str], ...] = (
    (
        "silver_925",
        ("silver_350", "silver_400", "silver_500", "silver_900", "silver_999"),
        "silver",
        "Срібло",
        "Silver",
    ),
    (
        "silver_gilded_925",
        ("silver_gilded_999",),
        "silver_gilded",
        "Срібло із золотим покриттям",
        "Gilded silver",
    ),
    ("gold_999", ("gold_900", "gold_1000"), "gold", "Золото", "Gold"),
)

# New categories that never had a row at all -- inserted only if missing (a
# fresh database already has them: migration 0003 seeds the collapsed
# dictionary directly).
NEW_MATERIALS: tuple[tuple[str, str, str], ...] = (
    ("zinc_alloy", "Сплав на основі цинку", "Zinc-based alloy"),
    ("not_specified", "Не вказано", "Not specified"),
    ("other_banknote", "Інший (банкнота)", "Other (banknote)"),
)

# Raw `material` text that is not already a dictionary code, resolved to one
# (app/reference_data/materials.py LEGACY_RAW_ALIASES, plus the Ukrainian bare
# words `nbu_metal` used to leave as text before it pointed at a real row).
MATERIAL_TEXT_ALIASES: dict[str, str] = {
    "bimetallic": "bimetal",
    "bimetallic_precious": "bimetal",
    "cupronickel": "copper_nickel",
    "banknote": "other_banknote",
    "срібло": "silver",
    "золото": "gold",
}

INSERT_MATERIAL = sa.text(
    "INSERT INTO materials (code, name_uk, name_en) VALUES (:code, :name_uk, :name_en) "
    "ON CONFLICT (code) DO NOTHING"
)
REPOINT_COMPOSITION = sa.text(
    "UPDATE catalog_items SET composition_id = "
    "(SELECT id FROM materials WHERE code = :new_code) "
    "WHERE composition_id IN (SELECT id FROM materials WHERE code = ANY(:old_codes))"
)
RENAME_MATERIAL = sa.text(
    "UPDATE materials SET code = :new_code, name_uk = :name_uk, name_en = :name_en "
    "WHERE code = :old_code"
)
DELETE_MATERIALS = sa.text("DELETE FROM materials WHERE code = ANY(:codes)")
RESOLVE_MATERIAL_CODE = sa.text(
    "UPDATE catalog_items SET composition_id = materials.id, material = NULL "
    "FROM materials WHERE catalog_items.composition_id IS NULL "
    "AND materials.code = lower(btrim(catalog_items.material))"
)
RESOLVE_MATERIAL_ALIAS = sa.text(
    "UPDATE catalog_items SET composition_id = "
    "(SELECT id FROM materials WHERE code = :code), material = NULL "
    "WHERE composition_id IS NULL AND lower(btrim(material)) = :alias"
)
RESOLVE_EDGE = sa.text(
    "UPDATE catalog_items SET edge_type_id = edge_types.id, edge = NULL "
    "FROM edge_types WHERE catalog_items.edge_type_id IS NULL "
    "AND edge_types.code = lower(btrim(catalog_items.edge))"
)
RESOLVE_QUALITY = sa.text(
    "UPDATE catalog_items SET quality_type_id = quality_types.id, quality = NULL "
    "FROM quality_types WHERE catalog_items.quality_type_id IS NULL "
    "AND quality_types.code = lower(btrim(catalog_items.quality))"
)
INSERT_EDGE_TYPE = sa.text(
    "INSERT INTO edge_types (code, name_uk, name_en) VALUES (:code, :name_uk, :name_en) "
    "ON CONFLICT (code) DO NOTHING"
)
INSERT_QUALITY_TYPE = sa.text(
    "INSERT INTO quality_types (code, name_uk, name_en) VALUES (:code, :name_uk, :name_en) "
    "ON CONFLICT (code) DO NOTHING"
)


def upgrade() -> None:
    op.create_table(
        "edge_types",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("name_uk", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
    )
    op.create_table(
        "quality_types",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("name_uk", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "edge_type_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "edge_types.id", ondelete="SET NULL", name="fk_catalog_items_edge_type_id"
            ),
        ),
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "quality_type_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "quality_types.id", ondelete="SET NULL", name="fk_catalog_items_quality_type_id"
            ),
        ),
    )

    connection = op.get_bind()

    for edge_type in EDGE_TYPES:
        connection.execute(
            INSERT_EDGE_TYPE,
            {"code": edge_type.code, "name_uk": edge_type.name_uk, "name_en": edge_type.name_en},
        )
    for quality_type in QUALITY_TYPES:
        connection.execute(
            INSERT_QUALITY_TYPE,
            {
                "code": quality_type.code,
                "name_uk": quality_type.name_uk,
                "name_en": quality_type.name_en,
            },
        )

    for code, name_uk, name_en in NEW_MATERIALS:
        connection.execute(INSERT_MATERIAL, {"code": code, "name_uk": name_uk, "name_en": name_en})

    for old_survivor_code, absorbed_codes, new_code, name_uk, name_en in MATERIAL_CONSOLIDATIONS:
        connection.execute(
            RENAME_MATERIAL,
            {
                "old_code": old_survivor_code,
                "new_code": new_code,
                "name_uk": name_uk,
                "name_en": name_en,
            },
        )
        connection.execute(
            REPOINT_COMPOSITION, {"new_code": new_code, "old_codes": list(absorbed_codes)}
        )
        connection.execute(DELETE_MATERIALS, {"codes": list(absorbed_codes)})

    connection.execute(RESOLVE_MATERIAL_CODE)
    for alias, code in MATERIAL_TEXT_ALIASES.items():
        connection.execute(RESOLVE_MATERIAL_ALIAS, {"code": code, "alias": alias})
    connection.execute(RESOLVE_EDGE)
    connection.execute(RESOLVE_QUALITY)


def downgrade() -> None:
    op.drop_column("catalog_items", "quality_type_id")
    op.drop_column("catalog_items", "edge_type_id")
    op.drop_table("quality_types")
    op.drop_table("edge_types")
