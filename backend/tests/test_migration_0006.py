"""Migration 0006 on a database filled at 0005.

Two things are worth running for real rather than asserting about the source.
The price key rebuild deletes rows, and it only works if the deduplication
picks the same groups the new constraint would reject -- a fixture with a
NULL-grade duplicate, a graded pair that must survive, and a pair the key does
not touch shows whether it does. The new columns are checked for the defaults
existing rows land on, since nothing backfills them.

Revision 0006 is the last one, so the rest of the suite runs against the same
schema; what this file adds is the state before it.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import _admin_url, _database_url, _run_alembic_to

# One shared item, one series, and four snapshots: ids 1 and 2 differ in
# nothing but are both grade NULL (only the tighter key sees them as a clash),
# 3 shares their timestamp under a grade, and 4 is a second NULL-grade snapshot
# an hour later that must survive.
FIXTURE = """
INSERT INTO currencies (code, name, symbol, decimal_places) VALUES
    ('UAH', 'Ukrainian hryvnia', '₴', 2);

INSERT INTO coin_series (id, country_id, name_original)
SELECT 900, id, 'Fixture series' FROM countries WHERE code = 'UA';

INSERT INTO catalog_items
    (id, country_id, series_id, collection_group, title_original, issue_year)
SELECT 900, id, 900, 'commemorative', 'Fixture coin', 2020
FROM countries WHERE code = 'UA';

INSERT INTO market_price_snapshots
    (id, catalog_item_id, source, grade, price, currency_code, observed_at)
VALUES
    (1, 900, 'UA-Coins', NULL, 100.00, 'UAH', '2026-01-01 10:00:00+00'),
    (2, 900, 'UA-Coins', NULL, 111.00, 'UAH', '2026-01-01 10:00:00+00'),
    (3, 900, 'UA-Coins', 'XF', 120.00, 'UAH', '2026-01-01 10:00:00+00'),
    (4, 900, 'UA-Coins', NULL, 130.00, 'UAH', '2026-01-01 11:00:00+00');
SELECT setval(pg_get_serial_sequence('market_price_snapshots', 'id'), 4);
"""


@pytest.fixture(scope="module")
async def migrated_connection() -> AsyncIterator[AsyncConnection]:
    db_name = f"coinkeeper_0006_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    url = _database_url(db_name)
    try:
        await asyncio.to_thread(_run_alembic_to, "0005", url)
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            for statement in filter(None, (s.strip() for s in FIXTURE.split(";"))):
                await connection.execute(text(statement))
        await engine.dispose()

        await asyncio.to_thread(_run_alembic_to, "0006", url)

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


async def test_existing_rows_get_the_defaults(migrated_connection: AsyncConnection) -> None:
    item = (
        (
            await migrated_connection.execute(
                text("SELECT status, quality, edited_fields FROM catalog_items WHERE id = 900")
            )
        )
        .mappings()
        .one()
    )
    assert item["status"] == "active"
    assert item["quality"] is None
    assert item["edited_fields"] is None

    is_official = (
        await migrated_connection.execute(
            text("SELECT is_official FROM coin_series WHERE id = 900")
        )
    ).scalar_one()
    assert is_official is False


async def test_the_null_grade_duplicate_is_collapsed_to_the_lowest_id(
    migrated_connection: AsyncConnection,
) -> None:
    ids = list(
        (
            await migrated_connection.execute(
                text("SELECT id FROM market_price_snapshots ORDER BY id")
            )
        ).scalars()
    )
    assert ids == [1, 3, 4]


async def test_the_key_now_sees_two_null_grades_as_one(
    migrated_connection: AsyncConnection,
) -> None:
    definition = (
        await migrated_connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'uq_market_price_snapshots_item_source_grade_observed'"
            )
        )
    ).scalar_one()
    assert "NULLS NOT DISTINCT" in definition

    with pytest.raises(IntegrityError):
        async with migrated_connection.begin_nested():
            await migrated_connection.execute(
                text(
                    "INSERT INTO market_price_snapshots "
                    "(catalog_item_id, source, grade, price, currency_code, observed_at) "
                    "VALUES (900, 'UA-Coins', NULL, 140.00, 'UAH', "
                    "'2026-01-01 10:00:00+00')"
                )
            )
