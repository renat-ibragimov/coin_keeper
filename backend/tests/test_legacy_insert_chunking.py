"""Bulk inserts are split so they fit PostgreSQL's bind parameter limit.

A multi-row INSERT spends one bind parameter per column per row, and
PostgreSQL takes at most 32767 in a statement. The first real migration run
died here: catalog_items is 3063 rows of 32 columns, close to 98k parameters,
sent as one statement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.legacy_migration.report import MigrationReport
from app.legacy_migration.runner import (
    MAX_BIND_PARAMETERS,
    MigrationOptions,
    MigrationRunner,
    chunk_rows,
    chunk_size_for,
)
from app.models import CatalogItem
from tests.fixtures.build_legacy_db import EXPECTED_COUNTS, build

POSTGRES_PARAMETER_LIMIT = 32767
# 32 columns wide, so this is comfortably past the limit in one statement.
EXTRA_CATALOG_ITEMS = 1500

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "migration-password"


def _rows(count: int, columns: int) -> list[dict[str, Any]]:
    return [{f"c{i}": i for i in range(columns)} for _ in range(count)]


# ------------------------------------------------------------------ the split


@pytest.mark.parametrize("columns", [1, 10, 21, 32, 45, 60])
def test_every_chunk_stays_under_the_parameter_limit(columns: int) -> None:
    rows = _rows(5000, columns)
    for chunk in chunk_rows(rows):
        assert len(chunk) * columns <= MAX_BIND_PARAMETERS
        assert len(chunk) * columns < POSTGRES_PARAMETER_LIMIT


def test_chunking_preserves_every_row_and_their_order() -> None:
    rows = [{"id": index, "b": index * 2, "c": index * 3} for index in range(2500)]
    assert [row for chunk in chunk_rows(rows) for row in chunk] == rows


def test_a_short_table_is_one_chunk() -> None:
    rows = _rows(10, 32)
    assert [len(chunk) for chunk in chunk_rows(rows)] == [10]


def test_no_chunks_for_no_rows() -> None:
    assert list(chunk_rows([])) == []


def test_an_absurdly_wide_row_still_yields_one_row_per_statement() -> None:
    """Never zero: a row wider than the budget still has to be inserted."""
    assert chunk_size_for(MAX_BIND_PARAMETERS * 2) == 1
    assert chunk_size_for(0) == MAX_BIND_PARAMETERS


# ---------------------------------------------------------------- end to end


@pytest.fixture
def large_legacy_db(tmp_path: Path) -> Path:
    return build(tmp_path / "large.db", extra_catalog_items=EXTRA_CATALOG_ITEMS)


def _options(path: Path, **overrides: object) -> MigrationOptions:
    base: dict[str, Any] = {
        "sqlite_path": path,
        "media_path": None,
        "owner_email": OWNER_EMAIL,
        "owner_password": OWNER_PASSWORD,
        "skip_media": True,
    }
    base.update(overrides)
    return MigrationOptions(**base)


async def _run(session: AsyncSession, options: MigrationOptions) -> MigrationReport:
    report = MigrationReport()
    return await MigrationRunner(session, options, report).run()


async def test_a_table_past_the_limit_migrates(
    db_session: AsyncSession, large_legacy_db: Path
) -> None:
    """Fails on the previous code with the 32767 parameter error."""
    expected = EXPECTED_COUNTS["catalog_items"] + EXTRA_CATALOG_ITEMS
    assert expected * 32 > POSTGRES_PARAMETER_LIMIT, "fixture too small to matter"

    report = await _run(db_session, _options(large_legacy_db))

    assert report.checks_passed, [c for c in report.checks if not c["passed"]]
    actual = await db_session.scalar(select(func.count()).select_from(CatalogItem))
    assert actual == expected


async def test_resuming_over_chunked_rows_creates_no_duplicates(
    db_session: AsyncSession, large_legacy_db: Path
) -> None:
    """ON CONFLICT covers it, but across chunk boundaries it needs proving."""
    await _run(db_session, _options(large_legacy_db))
    before = await db_session.scalar(select(func.count()).select_from(CatalogItem))

    await _run(db_session, _options(large_legacy_db, resume=True))
    after = await db_session.scalar(select(func.count()).select_from(CatalogItem))

    assert after == before

    distinct = await db_session.scalar(
        select(func.count(func.distinct(CatalogItem.id))).select_from(CatalogItem)
    )
    assert distinct == before


async def test_resume_fills_in_rows_left_by_an_interrupted_run(
    db_session: AsyncSession, large_legacy_db: Path
) -> None:
    """A run that died mid-table must be completable, not restarted by hand."""
    expected = EXPECTED_COUNTS["catalog_items"] + EXTRA_CATALOG_ITEMS
    await _run(db_session, _options(large_legacy_db))

    # Simulate an interruption: drop the tail of the table, keeping the rows an
    # early chunk would have written.
    survived = chunk_size_for(32)
    await db_session.execute(CatalogItem.__table__.delete().where(CatalogItem.id > survived))
    await db_session.flush()
    partial = await db_session.scalar(select(func.count()).select_from(CatalogItem))
    assert partial < expected

    await _run(db_session, _options(large_legacy_db, resume=True))

    restored = await db_session.scalar(select(func.count()).select_from(CatalogItem))
    assert restored == expected
