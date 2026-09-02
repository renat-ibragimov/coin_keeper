"""Read-only access to the legacy SQLite database.

The source of a migration is immutable by definition: it is a snapshot that has
already stopped changing, and nothing here may write to it. That is stated to
SQLite explicitly rather than merely intended, with both `mode=ro` and
`immutable=1`.

`immutable=1` is the part that matters in practice. The desktop application left
the database in WAL mode, and a plain read-only open still wants to create the
`-wal` and `-shm` sidecar files next to it. Copying just the `.db` file onto a
server and mounting the directory read-only — which is exactly what the runbook
in backend/README.md tells you to do — then fails. Depending on the permissions
it reports either "unable to open database file" or "attempt to write a readonly
database"; both are the same missing sidecar. Declaring the file immutable tells
SQLite the contents cannot change underneath it, so it skips journal and
shared-memory handling altogether.

The flag is a promise: if the file did change while open, the reader could see
corrupt data. For a migration source that promise holds — and the read-only
mount enforces it.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

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


def _read_only_uri(path: Path) -> str:
    """Build the SQLite URI for an immutable, read-only source.

    The path is percent-encoded: a space or a `?` in it would otherwise end the
    path or start another query parameter.
    """
    return f"file:{quote(str(path.resolve()))}?mode=ro&immutable=1"


@contextmanager
def open_legacy(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the SQLite file read-only and check it before reading."""
    if not path.is_file():
        msg = f"legacy database not found: {path}"
        raise LegacyDatabaseError(msg)

    connection = sqlite3.connect(_read_only_uri(path), uri=True)
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
