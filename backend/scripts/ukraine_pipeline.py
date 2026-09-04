"""The Ukrainian pipeline (stage 4.5, part B).

Links our catalogue to the National Bank, ua-coins.info and Wikipedia, fills
the gaps, repairs and merges what an earlier run of it left behind, takes the
official names, series and photographs, and records one price per coin. The
steps are in app/ukraine_pipeline/; this file is the command line around them.

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

from app.ukraine_pipeline import circ_bridge
from app.ukraine_pipeline import sources as source_module
from app.ukraine_pipeline.report import PipelineReport
from app.ukraine_pipeline.runner import (
    COMMEMORATIVE_STEPS,
    Options,
    PipelineError,
    Runner,
    parse_steps,
    source_summary,
)
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError

# The circ-* steps that actually read the mintage table; circ-titles and
# circ-photos work from the database and the "Про монети" pages alone.
MINTAGE_STEPS = frozenset({"circ-bridge", "circ-gaps", "circ-mintage"})

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
        help="comma-separated subset of the steps, in any order",
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
        "--duplicates-out",
        type=Path,
        help="where gaps writes the coins it did not create because one of our own "
        "records is already in that year and face value; --apply-review reads it back",
    )
    parser.add_argument(
        "--merge-out", type=Path, help="where to write the duplicate pairs for review"
    )
    parser.add_argument(
        "--apply-merge",
        type=Path,
        dest="merge_in",
        help="a reviewed merge CSV; the pairs marked yes are merged, one record kept",
    )
    parser.add_argument(
        "--circ-review-out",
        type=Path,
        help="where circ-bridge writes the candidates for review: two or more of our "
        "circulation records claiming the same denomination and year",
    )
    parser.add_argument(
        "--apply-circ-review",
        type=Path,
        dest="circ_review_in",
        help="a reviewed circ-bridge CSV to read decisions from",
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
    steps = parse_steps(args.steps)
    needs_commemorative = any(step in COMMEMORATIVE_STEPS for step in steps)
    needs_mintage = any(step in MINTAGE_STEPS for step in steps)
    report.options = {
        "dryRun": dry_run,
        "steps": list(steps),
        "limit": args.limit,
        "uaCoins": args.ua_coins,
        "sinceYear": args.since_year,
        "cacheDir": str(args.cache_dir) if args.cache_dir else None,
        "reviewOut": str(args.review_out) if args.review_out else None,
        "reviewIn": str(args.review_in) if args.review_in else None,
        "duplicatesOut": str(args.duplicates_out) if args.duplicates_out else None,
        "mergeOut": str(args.merge_out) if args.merge_out else None,
        "mergeIn": str(args.merge_in) if args.merge_in else None,
        "circReviewOut": str(args.circ_review_out) if args.circ_review_out else None,
        "circReviewIn": str(args.circ_review_in) if args.circ_review_in else None,
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
    if args.apply and ("photos" in steps or "circ-photos" in steps):
        storage = ObjectStorage(build_s3_client(settings), settings.s3_bucket)
        storage.ensure_bucket()

    with PoliteClient(cache_dir=args.cache_dir, pause_seconds=args.pause) as client:
        fetched = source_module.Sources()
        if needs_commemorative:
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

        mintage = (
            circ_bridge.fetch_mintage_table(client, log=log, warn=report.warn)
            if needs_mintage
            else []
        )

        options = Options(
            steps=steps,
            dry_run=dry_run,
            limit=args.limit,
            review_out=args.review_out,
            review_in=args.review_in,
            duplicates_out=args.duplicates_out,
            merge_out=args.merge_out,
            merge_in=args.merge_in,
            circ_review_out=args.circ_review_out,
            circ_review_in=args.circ_review_in,
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
                    mintage=mintage,
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
    checks = (
        ("review", args.review_in),
        ("merge", args.merge_in),
        ("circ review", args.circ_review_in),
    )
    for name, path in checks:
        if path is not None and not path.exists():
            print(f"{name} file not found: {path}", file=sys.stderr)
            return EXIT_USAGE
    log = Progress()
    try:
        return asyncio.run(_run(args, log))
    except PipelineError as exc:
        print(f"Pipeline stopped: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
