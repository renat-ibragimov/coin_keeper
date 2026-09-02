"""Command-line guards in scripts/migrate_legacy.py."""

from __future__ import annotations

import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.migrate_legacy import EXIT_USAGE, ReportPathError, check_report_path, main
from tests.fixtures.build_legacy_db import build


@pytest.fixture
def read_only_dir(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "mounted"
    directory.mkdir()
    directory.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
    try:
        yield directory
    finally:
        directory.chmod(stat.S_IRWXU)


def test_writable_directory_passes(tmp_path: Path) -> None:
    check_report_path(tmp_path / "report.json")
    # The probe leaves nothing behind.
    assert list(tmp_path.iterdir()) == []


def test_read_only_directory_is_refused(read_only_dir: Path) -> None:
    """The exact shape of the first real dry run: --report on the :ro mount."""
    with pytest.raises(ReportPathError) as caught:
        check_report_path(read_only_dir / "report.json")
    message = str(caught.value)
    assert "writable" in message
    # The message has to say what to do, not just that it went wrong.
    assert "migration-reports" in message


def test_missing_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReportPathError, match="does not exist"):
        check_report_path(tmp_path / "nope" / "report.json")


async def test_cli_stops_before_touching_the_database(tmp_path: Path, read_only_dir: Path) -> None:
    """Checked first, so a long run is never spent on a lost report."""
    legacy = build(tmp_path / "legacy.db")
    exit_code = await main(
        [
            "--sqlite",
            str(legacy),
            "--owner-email",
            "owner@example.com",
            "--skip-media",
            "--dry-run",
            "--report",
            str(read_only_dir / "report.json"),
        ]
    )
    assert exit_code == EXIT_USAGE
