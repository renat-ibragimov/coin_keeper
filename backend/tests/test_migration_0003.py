"""Migration 0003 against a fixture shaped like the real database.

The point of these tests is that nothing is lost. The production catalogue has
Russian titles where the original is blank, American denominations stored twice
(once in Russian, once in English), and material strings the uCoin importer
glued a coin heading onto. Each of those is a way for a data migration to drop
or mangle a row quietly, so each gets a fixture row and an assertion.

The migration runs for real, on its own throwaway database: an in-memory
imitation would test the imitation.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from alembic import command
from tests.conftest import _admin_url, _database_url

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# The legacy shape: Russian names, one label per denomination, material as prose.
FIXTURE = """
INSERT INTO currencies (code, name, symbol, decimal_places) VALUES
    ('UAH', 'Ukrainian hryvnia', '₴', 2),
    ('USD', 'US dollar', '$', 2);

INSERT INTO countries (id, code, name_original, name_ru, name_en, is_active) VALUES
    (1, NULL, 'США', 'США', 'США', true),
    (2, NULL, 'Украина', 'Украина', 'Украина', true),
    (3, NULL, 'СССР', 'СССР', 'USSR', true);
SELECT setval(pg_get_serial_sequence('countries', 'id'), 3);

INSERT INTO denominations (id, country_id, label_original, label_ru, label_en) VALUES
    (1, 1, '5 центов', '5 центов', '5 центов'),
    (2, 1, '5 cents', '5 cents', '5 cents'),
    (3, 1, '¼ доллара', '¼ доллара', '¼ доллара'),
    (4, 2, '2 гривны', '2 гривны', '2 гривны'),
    (5, 2, '200.000 карбованцев', '200.000 карбованцев', '200.000 карбованцев'),
    (6, 3, '1 рубль', '1 рубль', '1 рубль'),
    (7, 3, '½ копейки', '½ копейки', '½ копейки');
SELECT setval(pg_get_serial_sequence('denominations', 'id'), 7);

INSERT INTO coin_series (id, country_id, name_original, name_ru, name_en) VALUES
    (1, 2, 'Флора і фауна', 'Флора и фауна', 'Флора і фауна'),
    (2, 3, 'Советский Союз (1924 - 1958)', 'Советский Союз (1924 - 1958)', NULL);
SELECT setval(pg_get_serial_sequence('coin_series', 'id'), 2);

INSERT INTO catalog_items
    (id, country_id, series_id, denomination_id, collection_group,
     title_original, title_ru, title_en, issue_year, material, weight_grams)
VALUES
    -- A blank original with a Russian title: the Russian one is the original.
    (1, 2, 1, 4, 'commemorative', '', 'Дельфин', 'Дельфин', 2003,
     'Нейзильбер', NULL),
    -- The material with its dimensions attached.
    (2, 2, NULL, 4, 'circulation', 'Вдавленный трезубец', 'Вдавленный трезубец',
     'Вдавленный трезубец', 2116, 'Цинк с медным покрытием, 2.5g, ø 19mm', NULL),
    -- The importer glued the heading in front of the material.
    (3, 2, 1, 5, 'commemorative', 'Соня садовая', 'Соня садовая', 'Соня садовая', 1999,
     '2 гривны, 1999 Флора и фауна - Соня садовая Нейзильбер', NULL),
    -- An American coin on the Russian label of a duplicated denomination.
    (4, 1, NULL, 1, 'circulation', 'Liberty Nickel', 'Liberty Nickel', 'Liberty Nickel',
     1899, 'Copper-Nickel', NULL),
    -- The same denomination under its English label.
    (5, 1, NULL, 2, 'circulation', 'Buffalo Nickel', 'Buffalo Nickel', 'Buffalo Nickel',
     1913, 'Copper-Nickel', NULL),
    -- A mass already recorded must not be overwritten by the parser.
    (6, 3, 2, 6, 'circulation', 'Рубль', 'Рубль', 'Рубль', 1924,
     'Silver 0.900, 20g, ø 33.5mm', 19.995),
    -- A material nobody can read stays as it is.
    (7, 3, 2, 7, 'circulation', 'Полкопейки', 'Полкопейки', 'Полкопейки', 1925,
     'Unobtainium', NULL);
SELECT setval(pg_get_serial_sequence('catalog_items', 'id'), 7);
"""


def _run_alembic(url: str, revision: str) -> None:
    """Alembic reads the URL from settings, so the environment is the knob."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        command.upgrade(config, revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture(scope="module")
async def migrated_connection() -> AsyncIterator[AsyncConnection]:
    """A database taken to 0002, filled with the legacy shape, then to 0003."""
    db_name = f"coinkeeper_0003_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    url = _database_url(db_name)
    try:
        await asyncio.to_thread(_run_alembic, url, "0002")
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            for statement in filter(None, (s.strip() for s in FIXTURE.split(";"))):
                await connection.execute(text(statement))
        await engine.dispose()

        await asyncio.to_thread(_run_alembic, url, "0003")

        engine = create_async_engine(url)
        async with engine.connect() as connection:
            yield connection
        await engine.dispose()
    finally:
        admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


async def _rows(connection: AsyncConnection, sql: str, **params: Any) -> list[Any]:
    return list((await connection.execute(text(sql), params)).mappings())


async def _one(connection: AsyncConnection, sql: str, **params: Any) -> Any:
    return (await connection.execute(text(sql), params)).mappings().one()


# ------------------------------------------------------------------- titles
async def test_the_russian_title_becomes_the_original(
    migrated_connection: AsyncConnection,
) -> None:
    item = await _one(migrated_connection, "SELECT * FROM catalog_items WHERE id = 1")
    assert item["title_original"] == "Дельфин"
    assert item["original_lang"] == "uk"


async def test_the_russian_column_is_gone(migrated_connection: AsyncConnection) -> None:
    columns = await _rows(
        migrated_connection,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'catalog_items'",
    )
    names = {row["column_name"] for row in columns}
    assert "title_ru" not in names
    assert {"original_lang", "title_uk_source", "title_en_source", "composition_id"} <= names


async def test_the_search_index_no_longer_mentions_the_russian_column(
    migrated_connection: AsyncConnection,
) -> None:
    definition = (
        await migrated_connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'catalog_items_search_idx'")
        )
    ).scalar_one()
    assert "title_ru" not in definition
    assert "title_uk" in definition and "title_en" in definition


async def test_a_translation_repeating_the_original_is_not_a_translation(
    migrated_connection: AsyncConnection,
) -> None:
    """The desktop app wrote the same string into all three name columns."""
    titles = await _rows(migrated_connection, "SELECT id, title_en FROM catalog_items ORDER BY id")
    assert all(row["title_en"] is None for row in titles)
    series = await _one(migrated_connection, "SELECT * FROM coin_series WHERE id = 1")
    assert series["name_en"] is None
    assert series["name_original"] == "Флора і фауна"


async def test_the_issuer_language_follows_the_country(
    migrated_connection: AsyncConnection,
) -> None:
    langs = {
        row["id"]: row["original_lang"]
        for row in await _rows(migrated_connection, "SELECT id, original_lang FROM catalog_items")
    }
    assert langs[1] == "uk"
    assert langs[4] == "en"
    assert langs[6] == "ru"
    series = await _rows(
        migrated_connection, "SELECT id, original_lang FROM coin_series ORDER BY id"
    )
    assert [row["original_lang"] for row in series] == ["uk", "ru"]


# ---------------------------------------------------------------- countries
async def test_the_three_legacy_countries_keep_their_ids(
    migrated_connection: AsyncConnection,
) -> None:
    rows = {
        row["id"]: row
        for row in await _rows(migrated_connection, "SELECT * FROM countries WHERE id IN (1, 2, 3)")
    }
    assert rows[1]["code"] == "US"
    assert rows[2]["code"] == "UA"
    assert rows[2]["name_original"] == "Україна"
    assert rows[2]["name_uk"] == "Україна"
    assert rows[2]["name_en"] == "Ukraine"
    assert rows[2]["sort_order"] == 0
    assert rows[3]["code"] == "SUHH"
    assert rows[3]["name_original"] == "СССР"
    assert rows[3]["original_lang"] == "ru"


async def test_every_issuer_is_seeded_once(migrated_connection: AsyncConnection) -> None:
    total = (await migrated_connection.execute(text("SELECT count(*) FROM countries"))).scalar_one()
    distinct_codes = (
        await migrated_connection.execute(
            text("SELECT count(DISTINCT code) FROM countries WHERE code IS NOT NULL")
        )
    ).scalar_one()
    assert total == distinct_codes > 250
    poland = await _one(migrated_connection, "SELECT * FROM countries WHERE code = 'PL'")
    assert poland["name_original"] == "Polska"
    assert poland["is_active"] is False
    # The three legacy countries keep the state they had.
    assert all(
        row["is_active"]
        for row in await _rows(
            migrated_connection, "SELECT is_active FROM countries WHERE id IN (1, 2, 3)"
        )
    )


async def test_the_russian_country_column_is_gone(
    migrated_connection: AsyncConnection,
) -> None:
    for table in ("countries", "coin_series"):
        columns = await _rows(
            migrated_connection,
            "SELECT column_name FROM information_schema.columns WHERE table_name = :table",
            table=table,
        )
        assert "name_ru" not in {row["column_name"] for row in columns}


# ------------------------------------------------------------- denominations
async def test_labels_became_structure(migrated_connection: AsyncConnection) -> None:
    rows = {
        row["id"]: row for row in await _rows(migrated_connection, "SELECT * FROM denominations")
    }
    assert (rows[3]["value"], rows[3]["unit"], rows[3]["currency_code"]) == (
        Decimal("0.250"),
        "dollar",
        "USD",
    )
    assert (rows[4]["value"], rows[4]["unit"], rows[4]["currency_code"]) == (
        Decimal("2.000"),
        "hryvnia",
        "UAH",
    )
    assert (rows[5]["value"], rows[5]["unit"], rows[5]["currency_code"]) == (
        Decimal("200000.000"),
        "karbovanets",
        "UAK",
    )
    assert rows[7]["unit"] == "kopeck"
    assert rows[6]["currency_code"] == "SUR"


async def test_one_face_value_stored_twice_becomes_one_row(
    migrated_connection: AsyncConnection,
) -> None:
    """ "5 центов" and "5 cents" are the same denomination; the coins move over."""
    remaining = await _rows(migrated_connection, "SELECT id FROM denominations WHERE id IN (1, 2)")
    assert [row["id"] for row in remaining] == [1]
    coins = await _rows(
        migrated_connection,
        "SELECT id, denomination_id FROM catalog_items WHERE id IN (4, 5) ORDER BY id",
    )
    assert [row["denomination_id"] for row in coins] == [1, 1]


async def test_the_label_columns_are_gone(migrated_connection: AsyncConnection) -> None:
    columns = {
        row["column_name"]
        for row in await _rows(
            migrated_connection,
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'denominations'",
        )
    }
    assert not columns & {"label_original", "label_ru", "label_en", "value_minor_units"}
    assert {"value", "unit"} <= columns


# ----------------------------------------------------------------- material
async def test_material_becomes_a_dictionary_row_and_two_numbers(
    migrated_connection: AsyncConnection,
) -> None:
    rows = {
        row["id"]: row
        for row in await _rows(
            migrated_connection,
            "SELECT i.id, i.material, i.weight_grams, i.diameter_mm, m.code"
            " FROM catalog_items i LEFT JOIN materials m ON m.id = i.composition_id",
        )
    }
    assert rows[2]["code"] == "copper_plated_zinc"
    assert rows[2]["weight_grams"] == Decimal("2.500")
    assert rows[2]["diameter_mm"] == Decimal("19.00")
    assert rows[2]["material"] is None
    # Read from the end of a string the importer prefixed with the heading.
    assert rows[3]["code"] == "nickel_silver"
    assert rows[1]["code"] == "nickel_silver"


async def test_a_mass_already_recorded_is_left_alone(
    migrated_connection: AsyncConnection,
) -> None:
    row = await _one(
        migrated_connection, "SELECT weight_grams, diameter_mm FROM catalog_items WHERE id = 6"
    )
    assert row["weight_grams"] == Decimal("19.995")
    assert row["diameter_mm"] == Decimal("33.50")


async def test_an_unreadable_material_keeps_its_text(
    migrated_connection: AsyncConnection,
) -> None:
    row = await _one(
        migrated_connection,
        "SELECT material, composition_id FROM catalog_items WHERE id = 7",
    )
    assert row["material"] == "Unobtainium"
    assert row["composition_id"] is None


async def test_the_material_dictionary_is_seeded(
    migrated_connection: AsyncConnection,
) -> None:
    codes = {row["code"] for row in await _rows(migrated_connection, "SELECT code FROM materials")}
    assert {"silver_925", "nickel_silver", "bimetal", "copper_plated_zinc"} <= codes


async def test_the_missing_currencies_are_added(
    migrated_connection: AsyncConnection,
) -> None:
    codes = {row["code"] for row in await _rows(migrated_connection, "SELECT code FROM currencies")}
    assert {"UAK", "SUR"} <= codes
