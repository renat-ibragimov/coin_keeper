"""Migrate the desktop SQLite database into PostgreSQL.

Specification: docs/09-data-migration.md. The logic lives in
app/legacy_migration/; this file is the command line around it.

    python scripts/migrate_legacy.py \
        --sqlite /legacy-data/coinkeeper-2026-08-06.db \
        --media  /legacy-data/media \
        --owner-email <owner-email> \
        --dry-run

The owner's address and password are arguments and never defaults: the
repository is public (docs/09-data-migration.md).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.storage import ObjectStorage, build_s3_client
from app.db.session import dispose_engine, get_session_factory
from app.legacy_migration.reader import LegacyDatabaseError
from app.legacy_migration.report import MigrationReport
from app.legacy_migration.runner import MigrationError, MigrationOptions, MigrationRunner
from app.services.auth import WeakPasswordError

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SOURCE = 3
EXIT_CHECKS_FAILED = 4
EXIT_FAILED = 5

DEFAULT_REPORT = Path(__file__).resolve().parent / "migration-report.json"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate the legacy SQLite database into PostgreSQL."
    )
    parser.add_argument("--sqlite", required=True, type=Path, help="legacy .db file")
    parser.add_argument("--media", type=Path, help="directory with the legacy photos")
    parser.add_argument("--owner-email", required=True, help="collection owner's address")
    parser.add_argument(
        "--owner-password",
        nargs="?",
        const="",
        default=None,
        help="owner's password; pass the flag without a value to be prompted",
    )
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("--skip-media", action="store_true", help="do not process or upload images")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue on a database that already holds data",
    )
    parser.add_argument("--expect", type=Path, help="JSON profile of expected counts to enforce")
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT, help="where to write the report"
    )
    return parser.parse_args(argv)


def _resolve_password(args: argparse.Namespace) -> str:
    if args.dry_run and not args.owner_password:
        # Nothing is written, so no password is needed to produce a report.
        return "dry-run-placeholder-password"
    if args.owner_password:
        return str(args.owner_password)
    # Prompted rather than passed inline: keeps it out of shell history and
    # out of `ps` (docs/09-data-migration.md).
    return getpass.getpass("Owner password: ")


class ReportPathError(Exception):
    """The report cannot be written where it was asked to go."""


def check_report_path(path: Path) -> None:
    """Fail now rather than after the migration has run.

    The report is written last, so an unwritable destination costs the whole
    run before it is noticed. That is not hypothetical: the first real dry run
    pointed --report at the read-only mount holding the data and lost its report
    to EROFS at the very end.

    Permission bits are not consulted, a probe file is actually written: a
    read-only bind mount can look writable and refuse the write anyway, and the
    container runs as an unprivileged user whose access does not follow from the
    owner bits.
    """
    directory = path.parent if path.parent != Path() else Path.cwd()
    if not directory.exists():
        msg = f"report directory does not exist: {directory}"
        raise ReportPathError(msg)
    if not directory.is_dir():
        msg = f"report path is not inside a directory: {directory}"
        raise ReportPathError(msg)

    probe = directory / f".migrate-legacy-probe-{os.getpid()}"
    try:
        probe.write_bytes(b"")
    except OSError as exc:
        msg = (
            f"cannot write into {directory}: {exc.strerror}. "
            "Point --report at a writable directory; the data mount is read-only. "
            f"On the host: mkdir -p migration-reports && chown {os.getuid()} migration-reports"
        )
        raise ReportPathError(msg) from exc
    finally:
        # On a read-only filesystem the unlink fails too, and missing_ok only
        # covers FileNotFoundError — without this the guard would raise EROFS
        # instead of reporting it.
        with suppress(OSError):
            probe.unlink(missing_ok=True)


def _load_expectations(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


async def _run(args: argparse.Namespace) -> int:
    # Before anything else: a report we cannot write is a run we cannot judge.
    check_report_path(args.report)

    settings = get_settings()
    report = MigrationReport()
    options = MigrationOptions(
        sqlite_path=args.sqlite,
        media_path=args.media,
        owner_email=args.owner_email,
        owner_password=_resolve_password(args),
        dry_run=bool(args.dry_run),
        skip_media=bool(args.skip_media),
        resume=bool(args.resume),
        expectations=_load_expectations(args.expect),
    )

    if not options.dry_run:
        _validate_password(options.owner_password)

    storage = None
    if not options.skip_media and not options.dry_run and options.media_path is not None:
        storage = ObjectStorage(build_s3_client(settings), settings.s3_bucket)
        storage.ensure_bucket()

    async with get_session_factory()() as session:
        runner = MigrationRunner(session, options, report, storage=storage)
        result = await runner.run()

    result.finished_at = report.started_at
    result.write(args.report)
    for line in result.summary_lines():
        print(line)
    print(f"\nreport written to {args.report}")

    if not result.checks_passed:
        print("\nCHECKS FAILED - the migration did not reconcile.", file=sys.stderr)
        return EXIT_CHECKS_FAILED
    return EXIT_OK


def _validate_password(password: str) -> None:
    """Same rule as registration: no relaxed variant for seeding."""
    settings = get_settings()
    if len(password) < settings.password_min_length:
        raise WeakPasswordError(settings.password_min_length)


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return await _run(args)
    except WeakPasswordError as exc:
        print(
            f"Owner password rejected: it must be at least {exc.min_length} characters. "
            "Nothing was migrated.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    except LegacyDatabaseError as exc:
        print(f"Cannot read the legacy database: {exc}", file=sys.stderr)
        return EXIT_SOURCE
    except ReportPathError as exc:
        print(f"Report destination unusable: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except MigrationError as exc:
        print(f"Migration stopped: {exc}", file=sys.stderr)
        return EXIT_FAILED
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
