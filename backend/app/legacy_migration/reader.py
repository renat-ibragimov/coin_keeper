"""Read-only access to the legacy SQLite database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Tables the migration reads. Order is irrelevant here; the write order is in
# runner.py and follows docs/09-data-migration.md.
SOURCE_TABLES = (
    "currencies",
    "countries",
    "denominations",
    "coin_series",
    "catalog_items",
    "exchange_rates",
    "market_price_snapshots",
    "price_source_links",
    "collection_items",
    "expenses",
    "media_files",
    "ucoin_catalog_sources",
    "settings",
)


class LegacyDatabaseError(RuntimeError):
    """The source database is missing or unusable."""


@contextmanager
def open_legacy(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the SQLite file read-only and check it before reading."""
    if not path.is_file():
        msg = f"legacy database not found: {path}"
        raise LegacyDatabaseError(msg)

    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            msg = f"integrity_check failed: {result[0] if result else 'no result'}"
            raise LegacyDatabaseError(msg)
        yield connection
    finally:
        connection.close()


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def read_table(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """Whole table as dicts. The database is small enough to hold in memory."""
    if not table_exists(connection, table):
        return []
    rows = connection.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
    return [dict(row) for row in rows]


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    if not table_exists(connection, table):
        return 0
    row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
    return int(row[0])


def source_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {table: count_rows(connection, table) for table in SOURCE_TABLES}
