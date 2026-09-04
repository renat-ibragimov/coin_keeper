"""Three language slots for every named catalog entity.

Every named entity — a country, a series, a coin — gets the same three slots:
`*_original` in the issuer's own language (never translated, with
`original_lang` saying which language that is) plus `*_uk` and `*_en`, each
recording where the translation came from. Russian stops being a language of
its own: `title_ru`, `name_ru` and `label_ru` are dropped, and for the Soviet
part of the catalogue Russian is simply the original.

Three more things ride along, because they are the same problem — data kept as
prose instead of as structure:

* countries: every issuer seeded with its endonym and its Ukrainian and English
  names (app/reference_data/countries.json). Only Ukraine is seeded active;
  a country the database already holds keeps its own state and its id.
* denominations: "5 копеек" parsed into value + unit + currency, the label
  rendered per locale from there.
* materials: "Цинк с медным покрытием, 2.5g, ø 19mm" split into a dictionary
  row, a mass and a diameter.

Nothing is guessed: a denomination that cannot be parsed stops the migration
with the list, and a material that cannot be parsed keeps its text.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import sqlalchemy as sa

from alembic import op
from app.reference_data import countries as country_seed
from app.reference_data import materials as material_seed
from app.reference_data.denominations import (
    EXTRA_CURRENCIES,
    DenominationParseError,
    parse_label,
)

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRANSLATION_SOURCE = ("official", "llm", "manual")

# The issuer's language, by country code. Everything else falls back to the
# language the seed gives for the country.
ISSUER_LANGUAGE = {
    country_seed.UKRAINE_CODE: "uk",
    country_seed.USSR_CODE: "ru",
    country_seed.USA_CODE: "en",
}

SEARCH_INDEX_SQL = """
    CREATE INDEX catalog_items_search_idx ON catalog_items
    USING gin (to_tsvector('simple',
        coalesce(title_original,'') || ' ' || coalesce(title_uk,'') || ' ' ||
        coalesce(title_en,'')))
    WHERE NOT is_archived
"""
SEARCH_INDEX_SQL_WITH_RU = """
    CREATE INDEX catalog_items_search_idx ON catalog_items
    USING gin (to_tsvector('simple',
        coalesce(title_original,'') || ' ' || coalesce(title_uk,'') || ' ' ||
        coalesce(title_ru,'')       || ' ' || coalesce(title_en,'')))
    WHERE NOT is_archived
"""


def _report(line: str) -> None:
    """The migration says what it did; it does not change data silently."""
    print(f"[0003] {line}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------- upgrade
def upgrade() -> None:
    connection = op.get_bind()
    op.execute(
        "CREATE TYPE translation_source AS ENUM ("
        + ", ".join(f"'{value}'" for value in TRANSLATION_SOURCE)
        + ")"
    )
    # The Ukrainian pipeline stores ua-coins.info images when the NBU has none.
    op.execute("ALTER TYPE media_source ADD VALUE IF NOT EXISTS 'ua_coins'")

    _seed_currencies(connection)
    _seed_materials(connection)
    _upgrade_countries(connection)
    _upgrade_denominations(connection)
    _upgrade_series(connection)
    _upgrade_catalog_items(connection)


def _seed_currencies(connection: sa.Connection) -> None:
    for code, name, symbol, places in EXTRA_CURRENCIES:
        connection.execute(
            sa.text(
                "INSERT INTO currencies (code, name, symbol, decimal_places)"
                " VALUES (:code, :name, :symbol, :places)"
                " ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "name": name, "symbol": symbol, "places": places},
        )


def _seed_materials(connection: sa.Connection) -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("name_uk", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
    )
    connection.execute(
        sa.text(
            "INSERT INTO materials (code, name_uk, name_en) VALUES (:code, :name_uk, :name_en)"
        ),
        [
            {"code": item.code, "name_uk": item.name_uk, "name_en": item.name_en}
            for item in material_seed.MATERIALS
        ],
    )
    _report(f"materials seeded: {len(material_seed.MATERIALS)}")


# ------------------------------------------------------------------- countries
def _upgrade_countries(connection: sa.Connection) -> None:
    op.add_column(
        "countries",
        sa.Column("original_lang", sa.Text(), nullable=True, server_default="uk"),
    )
    op.add_column("countries", sa.Column("name_uk", sa.Text(), nullable=True))
    op.add_column(
        "countries",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
    )

    existing = connection.execute(
        sa.text("SELECT id, code, name_original, name_ru, name_en FROM countries")
    ).mappings()
    taken_codes: set[str] = set()
    unmatched: list[str] = []
    for row in existing:
        seed = _seed_for(row)
        if seed is None:
            unmatched.append(row["name_original"])
            connection.execute(
                sa.text("UPDATE countries SET original_lang = 'uk' WHERE id = :id"),
                {"id": row["id"]},
            )
            continue
        taken_codes.add(seed.code)
        connection.execute(
            sa.text(
                "UPDATE countries SET code = :code, name_original = :name_original,"
                " original_lang = :original_lang, name_uk = :name_uk, name_en = :name_en,"
                " sort_order = :sort_order WHERE id = :id"
            ),
            {
                "id": row["id"],
                "code": seed.code,
                "name_original": seed.name_original,
                "original_lang": seed.original_lang,
                "name_uk": seed.name_uk,
                "name_en": seed.name_en,
                "sort_order": seed.sort_order,
            },
        )

    # The legacy migration inserted countries with explicit ids. Its own
    # sequence reset covers that, but a seed that inserts rows must not depend
    # on someone else having remembered to run it.
    connection.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('countries', 'id'),"
            " coalesce((SELECT max(id) FROM countries), 1),"
            " (SELECT max(id) FROM countries) IS NOT NULL)"
        )
    )
    inserted = 0
    for seed in country_seed.load_countries():
        if seed.code in taken_codes:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO countries"
                " (code, name_original, original_lang, name_uk, name_en, sort_order, is_active)"
                " VALUES (:code, :name_original, :original_lang, :name_uk, :name_en,"
                " :sort_order, :is_active)"
                " ON CONFLICT (name_original) DO NOTHING"
            ),
            {
                "code": seed.code,
                "name_original": seed.name_original,
                "original_lang": seed.original_lang,
                "name_uk": seed.name_uk,
                "name_en": seed.name_en,
                "sort_order": seed.sort_order,
                "is_active": seed.is_active,
            },
        )
        inserted += 1

    op.alter_column("countries", "original_lang", nullable=False)
    op.drop_column("countries", "name_ru")
    _report(f"countries: {len(taken_codes)} matched, {inserted} inserted")
    if unmatched:
        _report(f"countries not in the seed, left as they were: {unmatched}")


def _seed_for(row: sa.RowMapping) -> country_seed.CountrySeed | None:
    if row["code"]:
        by_code = country_seed.find_by_code(row["code"])
        if by_code is not None:
            return by_code
    for name in (row["name_original"], row["name_ru"], row["name_en"]):
        if not name:
            continue
        found = country_seed.find_by_name(name)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------- denominations
def _upgrade_denominations(connection: sa.Connection) -> None:
    op.add_column("denominations", sa.Column("value", sa.Numeric(14, 3), nullable=True))
    op.add_column("denominations", sa.Column("unit", sa.Text(), nullable=True))

    rows = connection.execute(
        sa.text(
            "SELECT d.id, d.country_id, d.label_original, c.code AS country_code"
            " FROM denominations d JOIN countries c ON c.id = d.country_id"
            " ORDER BY d.id"
        )
    ).mappings()

    parsed: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in rows:
        try:
            value = parse_label(row["label_original"], country_code=row["country_code"])
        except DenominationParseError as exc:
            failures.append(f"#{row['id']} {row['label_original']!r}: {exc}")
            continue
        parsed.append(
            {
                "id": row["id"],
                "country_id": row["country_id"],
                "value": value.value,
                "unit": value.unit,
                "currency_code": value.currency_code,
                "sort_order": value.minor_units,
            }
        )
    if failures:
        # Guessing a face value would put wrong numbers in front of the owner.
        message = "denominations that cannot be parsed:\n  " + "\n  ".join(failures)
        raise RuntimeError(message)

    for row in parsed:
        connection.execute(
            sa.text(
                "UPDATE denominations SET value = :value, unit = :unit,"
                " currency_code = :currency_code, sort_order = :sort_order WHERE id = :id"
            ),
            row,
        )

    merged = _merge_duplicate_denominations(connection, parsed)

    op.drop_constraint(
        "uq_denominations_country_id_label_original", "denominations", type_="unique"
    )
    for column in ("value_minor_units", "label_original", "label_ru", "label_en"):
        op.drop_column("denominations", column)
    op.alter_column("denominations", "value", nullable=False)
    op.alter_column("denominations", "unit", nullable=False)
    op.alter_column("denominations", "currency_code", nullable=False)
    op.create_unique_constraint(
        "uq_denominations_country_id_currency_code_unit_value",
        "denominations",
        ["country_id", "currency_code", "unit", "value"],
    )
    _report(f"denominations parsed: {len(parsed)}, merged as duplicates: {merged}")


def _merge_duplicate_denominations(connection: sa.Connection, parsed: list[dict[str, Any]]) -> int:
    """Two labels for one face value ("5 центов" and "5 cents") are one row.

    The legacy catalogue holds both the Russian and the English label for the
    American denominations. Under the natural key they are the same
    denomination, so the coins move to the lowest id and the extra row goes.
    """
    groups: dict[tuple[Any, ...], list[int]] = {}
    for row in parsed:
        key = (row["country_id"], row["currency_code"], row["unit"], Decimal(row["value"]))
        groups.setdefault(key, []).append(row["id"])

    duplicates = {key: ids for key, ids in groups.items() if len(ids) > 1}
    if not duplicates:
        return 0

    # collection_goals keeps denomination ids in a JSONB array. The table is
    # unused in the MVP; the day it is not, merging has to remap those arrays
    # rather than quietly leave a goal pointing at a deleted row.
    goals = connection.execute(
        sa.text("SELECT count(*) FROM collection_goals WHERE denomination_ids IS NOT NULL")
    ).scalar_one()
    if goals:
        message = (
            f"{goals} collection_goals rows list denomination ids; merging duplicate "
            "denominations would leave those goals pointing at deleted rows"
        )
        raise RuntimeError(message)

    merged = 0
    for key, ids in duplicates.items():
        keep, *extras = sorted(ids)
        move = sa.text(
            "UPDATE catalog_items SET denomination_id = :keep WHERE denomination_id IN :extras"
        ).bindparams(sa.bindparam("extras", expanding=True))
        connection.execute(move, {"keep": keep, "extras": extras})
        remove = sa.text("DELETE FROM denominations WHERE id IN :extras").bindparams(
            sa.bindparam("extras", expanding=True)
        )
        connection.execute(remove, {"extras": extras})
        merged += len(extras)
        _report(f"denomination {key[3]} {key[2]}: kept #{keep}, merged {extras}")
    return merged


# ---------------------------------------------------------------------- series
def _upgrade_series(connection: sa.Connection) -> None:
    op.add_column(
        "coin_series",
        sa.Column("original_lang", sa.Text(), nullable=True, server_default="uk"),
    )
    op.add_column("coin_series", sa.Column("name_uk", sa.Text(), nullable=True))
    op.add_column(
        "coin_series",
        sa.Column(
            "name_uk_source",
            sa.Enum(*TRANSLATION_SOURCE, name="translation_source", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "coin_series",
        sa.Column(
            "name_en_source",
            sa.Enum(*TRANSLATION_SOURCE, name="translation_source", create_type=False),
            nullable=True,
        ),
    )
    connection.execute(sa.text(_issuer_language_update("coin_series")))
    # A translated slot that merely repeats the original is not a translation:
    # the legacy importer filled all three columns with the same string.
    connection.execute(
        sa.text(
            "UPDATE coin_series SET name_en = NULL"
            " WHERE name_en IS NOT NULL AND btrim(name_en) = btrim(name_original)"
        )
    )
    op.alter_column("coin_series", "original_lang", nullable=False)
    op.drop_column("coin_series", "name_ru")


def _issuer_language_update(table: str) -> str:
    cases = " ".join(
        f"WHEN c.code = '{code}' THEN '{language}'" for code, language in ISSUER_LANGUAGE.items()
    )
    # The table name and the cases come from constants in this file, not from
    # anything a user can reach.
    return (
        f"UPDATE {table} AS t SET original_lang = CASE {cases}"  # noqa: S608
        " ELSE coalesce(c.original_lang, 'uk') END"
        " FROM countries c WHERE c.id = t.country_id"
    )


# --------------------------------------------------------------- catalog items
def _upgrade_catalog_items(connection: sa.Connection) -> None:
    # Ukrainian by default, the way the interface is: a record created without
    # a language named is a Ukrainian one until someone says otherwise.
    op.add_column(
        "catalog_items",
        sa.Column("original_lang", sa.Text(), nullable=True, server_default="uk"),
    )
    for column in ("title_uk_source", "title_en_source"):
        op.add_column(
            "catalog_items",
            sa.Column(
                column,
                sa.Enum(*TRANSLATION_SOURCE, name="translation_source", create_type=False),
                nullable=True,
            ),
        )
    op.add_column(
        "catalog_items",
        sa.Column(
            "composition_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "materials.id", ondelete="SET NULL", name="fk_catalog_items_composition_id"
            ),
            nullable=True,
        ),
    )

    connection.execute(sa.text(_issuer_language_update("catalog_items")))

    # An empty original with a Russian title: the Russian one is the original.
    moved = connection.execute(
        sa.text(
            "UPDATE catalog_items SET title_original = title_ru"
            " WHERE btrim(coalesce(title_original, '')) = ''"
            " AND btrim(coalesce(title_ru, '')) <> ''"
        )
    ).rowcount
    # American coins are named in English; that name is the original.
    promoted = connection.execute(
        sa.text(
            "UPDATE catalog_items AS i SET title_original = i.title_en"
            " FROM countries c"
            " WHERE c.id = i.country_id AND c.code = :usa"
            " AND btrim(coalesce(i.title_en, '')) <> ''"
            " AND btrim(i.title_en) <> btrim(i.title_original)"
        ),
        {"usa": country_seed.USA_CODE},
    ).rowcount
    cleared = 0
    for column in ("title_uk", "title_en"):
        cleared += connection.execute(
            # The column name is one of the two literals in the loop above.
            sa.text(
                f"UPDATE catalog_items SET {column} = NULL"  # noqa: S608
                f" WHERE {column} IS NOT NULL AND btrim({column}) = btrim(title_original)"
            )
        ).rowcount

    op.alter_column("catalog_items", "original_lang", nullable=False)
    op.drop_column("catalog_items", "title_ru")
    op.execute("DROP INDEX IF EXISTS catalog_items_search_idx")
    op.execute(SEARCH_INDEX_SQL)
    _report(
        f"titles: {moved} originals taken from the Russian slot,"
        f" {promoted} American originals taken from the English slot,"
        f" {cleared} translated slots cleared as duplicates of the original"
    )

    _split_material(connection)


def _split_material(connection: sa.Connection) -> None:
    material_ids = {
        row["code"]: row["id"]
        for row in connection.execute(sa.text("SELECT id, code FROM materials")).mappings()
    }
    rows = connection.execute(
        sa.text(
            "SELECT id, material, weight_grams, diameter_mm FROM catalog_items"
            " WHERE material IS NOT NULL AND btrim(material) <> ''"
        )
    ).mappings()

    recognised = 0
    filled_mass = 0
    filled_diameter = 0
    unrecognised: dict[str, int] = {}
    for row in rows:
        parsed = material_seed.parse_material(row["material"])
        if parsed.composition is None:
            unrecognised[row["material"]] = unrecognised.get(row["material"], 0) + 1
            continue
        values: dict[str, Any] = {
            "id": row["id"],
            "composition_id": material_ids[parsed.composition],
        }
        assignments = ["composition_id = :composition_id", "material = NULL"]
        if parsed.weight_grams is not None and row["weight_grams"] is None:
            assignments.append("weight_grams = :weight_grams")
            values["weight_grams"] = parsed.weight_grams
            filled_mass += 1
        if parsed.diameter_mm is not None and row["diameter_mm"] is None:
            assignments.append("diameter_mm = :diameter_mm")
            values["diameter_mm"] = parsed.diameter_mm
            filled_diameter += 1
        connection.execute(
            # The assignments are literals chosen above; the values are bound.
            sa.text(f"UPDATE catalog_items SET {', '.join(assignments)} WHERE id = :id"),  # noqa: S608
            values,
        )
        recognised += 1

    _report(
        f"material: {recognised} items given a composition,"
        f" {filled_mass} masses and {filled_diameter} diameters filled in"
    )
    if unrecognised:
        _report(f"material left as text on {sum(unrecognised.values())} items:")
        for text, count in sorted(unrecognised.items(), key=lambda pair: -pair[1]):
            _report(f"    {count:>5}  {text}")


# ------------------------------------------------------------------- downgrade
def downgrade() -> None:
    """Structural only.

    The Russian slots come back empty and the denomination labels are rendered
    rather than restored: this migration deliberately throws the Russian
    wording away, and no downgrade can invent it back. Restore from a dump if
    the old text matters.
    """
    connection = op.get_bind()

    op.drop_constraint("fk_catalog_items_composition_id", "catalog_items", type_="foreignkey")
    op.drop_column("catalog_items", "composition_id")
    op.drop_column("catalog_items", "title_en_source")
    op.drop_column("catalog_items", "title_uk_source")
    op.drop_column("catalog_items", "original_lang")
    op.add_column("catalog_items", sa.Column("title_ru", sa.Text(), nullable=True))
    op.execute("DROP INDEX IF EXISTS catalog_items_search_idx")
    op.execute(SEARCH_INDEX_SQL_WITH_RU)

    op.drop_column("coin_series", "name_en_source")
    op.drop_column("coin_series", "name_uk_source")
    op.drop_column("coin_series", "name_uk")
    op.drop_column("coin_series", "original_lang")
    op.add_column("coin_series", sa.Column("name_ru", sa.Text(), nullable=True))

    op.drop_constraint(
        "uq_denominations_country_id_currency_code_unit_value", "denominations", type_="unique"
    )
    op.add_column("denominations", sa.Column("value_minor_units", sa.BigInteger(), nullable=True))
    op.add_column("denominations", sa.Column("label_original", sa.Text(), nullable=True))
    op.add_column("denominations", sa.Column("label_ru", sa.Text(), nullable=True))
    op.add_column("denominations", sa.Column("label_en", sa.Text(), nullable=True))
    _restore_denomination_labels(connection)
    op.alter_column("denominations", "label_original", nullable=False)
    op.alter_column("denominations", "currency_code", nullable=True)
    op.drop_column("denominations", "unit")
    op.drop_column("denominations", "value")
    op.create_unique_constraint(
        "uq_denominations_country_id_label_original",
        "denominations",
        ["country_id", "label_original"],
    )

    op.drop_column("countries", "sort_order")
    op.drop_column("countries", "name_uk")
    op.drop_column("countries", "original_lang")
    op.add_column("countries", sa.Column("name_ru", sa.Text(), nullable=True))

    op.drop_table("materials")
    op.execute("DROP TYPE translation_source")


def _restore_denomination_labels(connection: sa.Connection) -> None:
    from app.reference_data.denominations import UNITS, render_label

    rows = connection.execute(sa.text("SELECT id, value, unit FROM denominations")).mappings()
    for row in rows:
        label = render_label(Decimal(row["value"]), row["unit"], "uk")
        connection.execute(
            sa.text(
                "UPDATE denominations SET label_original = :label,"
                " value_minor_units = :minor WHERE id = :id"
            ),
            {
                "id": row["id"],
                "label": label,
                "minor": int(Decimal(row["value"]) * UNITS[row["unit"]].minor_units)
                if row["unit"] in UNITS
                else None,
            },
        )
