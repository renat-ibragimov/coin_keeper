"""Migration 0007 on a database filled at 0006.

The migration rewrites rows, so it is run for real against the four shapes the
catalogue actually holds: a code with no composition, the same code on an item
that already has one, a bare metal, and an alloy name that must not be touched.

Revision 0007 is the last one, so the rest of the suite runs against the same
schema; what this file adds is the state before it.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import _admin_url, _database_url, _run_alembic_to

# 901 is the card that started this: a dictionary code and nothing else.
# 902 carries the same code next to a composition the pipeline had already
# filled in, 903 a bare metal, 904 a real alloy name the migration must leave
# exactly as it stands.
FIXTURE = """
INSERT INTO catalog_items
    (id, country_id, collection_group, title_original, issue_year, material, composition_id)
SELECT 901, country.id, 'commemorative', 'Code only', 2023, 'nickel_silver', NULL
FROM countries AS country WHERE country.code = 'UA';

INSERT INTO catalog_items
    (id, country_id, collection_group, title_original, issue_year, material, composition_id)
SELECT 902, country.id, 'commemorative', 'Code beside a composition', 2023, 'Nickel_Silver ',
       material.id
FROM countries AS country, materials AS material
WHERE country.code = 'UA' AND material.code = 'silver';

INSERT INTO catalog_items
    (id, country_id, collection_group, title_original, issue_year, material, composition_id)
SELECT 903, country.id, 'commemorative', 'Bare metal', 2023, 'silver', NULL
FROM countries AS country WHERE country.code = 'UA';

INSERT INTO catalog_items
    (id, country_id, collection_group, title_original, issue_year, material, composition_id)
SELECT 904, country.id, 'commemorative', 'Alloy name', 2023, 'срібло', NULL
FROM countries AS country WHERE country.code = 'UA';
"""

QUERY = """
SELECT item.material, material.code AS composition
FROM catalog_items AS item
LEFT JOIN materials AS material ON material.id = item.composition_id
WHERE item.id = :item_id
"""


@pytest.fixture(scope="module")
async def migrated_connection() -> AsyncIterator[AsyncConnection]:
    db_name = f"coinkeeper_0007_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    url = _database_url(db_name)
    try:
        await asyncio.to_thread(_run_alembic_to, "0006", url)
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            for statement in filter(None, (s.strip() for s in FIXTURE.split(";"))):
                await connection.execute(text(statement))
        await engine.dispose()

        await asyncio.to_thread(_run_alembic_to, "0007", url)

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


async def row(connection: AsyncConnection, item_id: int) -> dict[str, str | None]:
    result = await connection.execute(text(QUERY), {"item_id": item_id})
    return dict(result.mappings().one())


async def test_a_code_becomes_the_dictionary_row_it_names(
    migrated_connection: AsyncConnection,
) -> None:
    assert await row(migrated_connection, 901) == {
        "material": None,
        "composition": "nickel_silver",
    }


async def test_a_code_beside_a_composition_only_loses_the_text(
    migrated_connection: AsyncConnection,
) -> None:
    """Whatever filled the composition knew more than the leftover token."""
    assert await row(migrated_connection, 902) == {"material": None, "composition": "silver"}


async def test_a_bare_metal_is_now_a_code_too(
    migrated_connection: AsyncConnection,
) -> None:
    """ "silver"/"gold" are dictionary codes as of 2026-09-12 (no fineness in
    the dictionary at all, docs/04-business-rules.md, §13a), so a bare metal
    now resolves the same way "nickel_silver" always did."""
    assert await row(migrated_connection, 903) == {"material": None, "composition": "silver"}


async def test_an_alloy_name_is_left_alone(migrated_connection: AsyncConnection) -> None:
    assert await row(migrated_connection, 904) == {"material": "срібло", "composition": None}
