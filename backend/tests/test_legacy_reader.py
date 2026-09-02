"""Opening the legacy database (app/legacy_migration/reader.py)."""

from __future__ import annotations

import shutil
import sqlite3
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.legacy_migration.reader import _read_only_uri, count_rows, open_legacy
from app.legacy_migration.report import MigrationReport
from app.legacy_migration.runner import MigrationOptions, MigrationRunner
from tests.fixtures.build_legacy_db import EXPECTED_COUNTS, build

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "migration-password"


@pytest.fixture
def wal_database_in_read_only_dir(tmp_path: Path) -> Iterator[Path]:
    """The shape the runbook produces on the server.

    The desktop application left the database in WAL mode; `scp` copies the
    `.db` file alone, without its `-wal` and `-shm` siblings; and the runbook
    mounts the directory read-only. A plain read-only open tries to recreate
    those sidecar files and fails.
    """
    origin = tmp_path / "source"
    origin.mkdir()
    source = build(origin / "legacy.db")
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    mounted = tmp_path / "mounted"
    mounted.mkdir()
    # Only the database file, exactly as scp would leave it.
    shutil.copy(source, mounted / "legacy.db")

    mounted.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    try:
        yield mounted / "legacy.db"
    finally:
        # Restored so pytest can clean the directory up.
        mounted.chmod(stat.S_IRWXU)


def test_uri_declares_the_source_immutable() -> None:
    uri = _read_only_uri(Path("/legacy-data/legacy.db"))
    assert "mode=ro" in uri
    assert "immutable=1" in uri


def test_uri_escapes_the_path(tmp_path: Path) -> None:
    """A space or a question mark would otherwise break the URI apart."""
    awkward = tmp_path / "a b?c"
    uri = _read_only_uri(awkward / "legacy.db")
    assert "a%20b%3Fc" in uri
    assert uri.endswith("?mode=ro&immutable=1")


def test_opens_a_wal_database_from_a_read_only_directory(
    wal_database_in_read_only_dir: Path,
) -> None:
    """Regression: this is the first real dry run on the server.

    Fails on a plain `mode=ro` open, because SQLite wants to create the WAL
    sidecar files and cannot: "unable to open database file" when it may not
    even open the directory, "attempt to write a readonly database" when it may.
    """
    with open_legacy(wal_database_in_read_only_dir) as connection:
        assert count_rows(connection, "catalog_items") == EXPECTED_COUNTS["catalog_items"]


def test_nothing_is_written_next_to_the_source(tmp_path: Path) -> None:
    """Not one sidecar file appears beside a database the migration reads."""
    directory = tmp_path / "writable"
    directory.mkdir()
    database = build(directory / "legacy.db")
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    for sidecar in directory.glob("legacy.db-*"):
        sidecar.unlink()

    with open_legacy(database) as connection:
        count_rows(connection, "catalog_items")

    assert sorted(p.name for p in directory.iterdir()) == ["legacy.db"]


async def test_dry_run_over_a_read_only_mount(
    db_session: AsyncSession, wal_database_in_read_only_dir: Path
) -> None:
    """The whole runbook step: a dry run against the mounted data."""
    report = MigrationReport()
    runner = MigrationRunner(
        db_session,
        MigrationOptions(
            sqlite_path=wal_database_in_read_only_dir,
            media_path=None,
            owner_email=OWNER_EMAIL,
            owner_password=OWNER_PASSWORD,
            dry_run=True,
            skip_media=True,
        ),
        report,
    )
    result = await runner.run()

    assert result.checks_passed, [c for c in result.checks if not c["passed"]]
    assert result.migrated["catalog_items"] == EXPECTED_COUNTS["catalog_items"]
