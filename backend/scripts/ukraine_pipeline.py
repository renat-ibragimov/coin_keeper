"""The Ukrainian pipeline (stage 4.5, part B).

Links our catalogue to the National Bank, ua-coins.info and Wikipedia, fills
the gaps, takes the official names, series and photographs, and records one
price per coin. The steps are in app/ukraine_pipeline/; this file is the
command line around them.

    python scripts/ukraine_pipeline.py --dry-run --report /reports/ukraine.json \
        --cache-dir /reports/ukraine-cache

Nothing is written without --apply. The runbook — the order to run the steps
in, and what to look at between them — is in backend/README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from app.ukraine_pipeline import sources as source_module
from app.ukraine_pipeline.report import PipelineReport
from app.ukraine_pipeline.runner import Options, PipelineError, Runner, parse_steps, source_summary
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SOURCE = 3
EXIT_FAILED = 5

DEFAULT_REPORT = Path(__file__).resolve().parent / "ukraine-pipeline-report.json"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="The Ukrainian catalogue pipeline.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--cache-dir", type=Path, help="disk cache for fetched pages and images")
    parser.add_argument(
        "--steps",
        help="comma-separated subset of bridge,gaps,titles,series,photos,prices",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to the database and to object storage; without it nothing is written",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit form of the default: read, decide, report, change nothing",
    )
    parser.add_argument(
        "--limit", type=int, help="stop a step after N items (photos and gaps take it)"
    )
    parser.add_argument(
        "--review-out", type=Path, help="where to write the bridge candidates for review"
    )
    parser.add_argument(
        "--apply-review", type=Path, dest="review_in", help="a reviewed CSV to read decisions from"
    )
    parser.add_argument(
        "--ua-coins",
        choices=(
            source_module.MODE_AUTO,
            source_module.MODE_LIVE,
            source_module.MODE_WAYBACK,
            source_module.MODE_SKIP,
        ),
        default=source_module.MODE_AUTO,
    )
    parser.add_argument("--pause", type=float, default=0.45, help="seconds between requests")
    parser.add_argument("--since-year", type=int, help="only coins issued in or after this year")
    return parser.parse_args(argv)


class Progress:
    """Timestamped progress on stderr; the report is the record on stdout."""

    def __init__(self, stream: IO[str] = sys.stderr) -> None:
        self.stream = stream

    def __call__(self, message: str) -> None:
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        print(f"[{stamp}] {message}", file=self.stream, flush=True)


async def _run(args: argparse.Namespace, log: Callable[[str], None]) -> int:
    from app.core.config import get_settings
    from app.core.storage import ObjectStorage, build_s3_client
    from app.db.session import dispose_engine, get_session_factory

    report = PipelineReport()
    dry_run = not args.apply
    report.options = {
        "dryRun": dry_run,
        "steps": list(parse_steps(args.steps)),
        "limit": args.limit,
        "uaCoins": args.ua_coins,
        "sinceYear": args.since_year,
        "cacheDir": str(args.cache_dir) if args.cache_dir else None,
        "reviewOut": str(args.review_out) if args.review_out else None,
        "reviewIn": str(args.review_in) if args.review_in else None,
    }
    report.assumptions = [
        "Only shared Ukrainian records take part; personal items belong to their authors.",
        "The National Bank is the source of names, series and photographs; ua-coins.info "
        "of prices and of the images the NBU has none of.",
        "A cluster is one coin across the three sources; a link is written only above the "
        "confidence threshold, everything else goes to the review CSV.",
    ]

    settings = get_settings()
    storage: ObjectStorage | None = None
    if args.apply and "photos" in parse_steps(args.steps):
        storage = ObjectStorage(build_s3_client(settings), settings.s3_bucket)
        storage.ensure_bucket()

    with PoliteClient(cache_dir=args.cache_dir, pause_seconds=args.pause) as client:
        try:
            fetched = source_module.fetch_sources(
                client,
                log=log,
                warn=report.warn,
                ua_coins_mode=args.ua_coins,
                since_year=args.since_year,
            )
        except SourceUnreachableError as exc:
            print(f"Source unreachable: {exc}", file=sys.stderr)
            return EXIT_SOURCE
        report.sources = source_summary(fetched)
        if not fetched.nbu:
            print("The NBU catalogue could not be read; nothing to do.", file=sys.stderr)
            return EXIT_SOURCE

        options = Options(
            steps=parse_steps(args.steps),
            dry_run=dry_run,
            limit=args.limit,
            review_out=args.review_out,
            review_in=args.review_in,
            report_path=args.report,
        )
        try:
            async with get_session_factory()() as session:
                runner = Runner(
                    session=session,
                    client=client,
                    sources=fetched,
                    report=report,
                    options=options,
                    log=log,
                    storage=storage,
                )
                await runner.run()
        finally:
            await dispose_engine()
        report.http = {
            "requests": client.requests_made,
            "cacheHits": client.cache_hits,
            "deadHosts": client.dead_hosts,
        }

    report.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
    report.write(args.report)
    for line in report.summary_lines():
        print(line)
    print(f"\nreport written to {args.report}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.apply and args.dry_run:
        print("--apply and --dry-run contradict each other", file=sys.stderr)
        return EXIT_USAGE
    if args.review_in is not None and not args.review_in.exists():
        print(f"review file not found: {args.review_in}", file=sys.stderr)
        return EXIT_USAGE
    log = Progress()
    try:
        return asyncio.run(_run(args, log))
    except PipelineError as exc:
        print(f"Pipeline stopped: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
