"""scan_coin_photo_packaging — which stored Ukrainian coin photos are actually
packaging, and which of those have a clean ua-coins.info replacement.

The circulation-commemorative rolls ("Ми сильні. Ми разом. <область>" and
the like, docs/05-integrations.md section 9) are read off a souvenir roll
card, and the roll card's own photograph is the roll — a tube, ribbons, the
whole product shot — not the coin (app/ukraine_pipeline/sources.py:roll_coin,
app/ukraine_recon/series_map.json's "Ми сильні" note). Nothing upstream ever
checked that; this is the first pass that does, geometrically
(app/ukraine_pipeline/classify_coin_photos.py), against every shared
Ukrainian record's stored photo, not only the nine we already know about.

    docker compose run --rm -v "$PWD/migration-reports:/reports" \\
      api python scripts/scan_coin_photo_packaging.py --dry-run \\
        --out /reports/coin-photo-packaging.csv \\
        --report /reports/coin-photo-packaging.json \\
        --cache-dir /reports/ukraine-cache

Nothing is written without --apply, and --apply always reads back a CSV
`--apply-review` produced by a person: this script never replaces a photo on
its own judgment. A row's `replacementUrl` is filled in only for a "Ми
сильні. Ми разом." title matched against the ua-coins.info "розмінні та
обігові" listing (app/ukraine_pipeline/roll_photos.py) — deliberately narrow,
see that module's docstring; every other packaging verdict is reported with
an empty `replacementUrl` for a person to fill in by hand, exactly the CSV
review idiom the rest of this pipeline already uses.

    docker compose run --rm -v "$PWD/migration-reports:/reports" \\
      api python scripts/scan_coin_photo_packaging.py --apply \\
        --apply-review /reports/coin-photo-packaging.csv \\
        --report /reports/coin-photo-packaging-apply.json \\
        --cache-dir /reports/ukraine-cache
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.images import process_image
from app.core.media_keys import (
    catalog_base,
    preview_key_of,
    primary_key_of,
    stored_variants,
    variant_key,
)
from app.core.storage import ObjectStorage
from app.models import CatalogItem, MediaFile
from app.models.enums import MediaRole, MediaSource
from app.ukraine_pipeline.catalog import ukraine_country_id
from app.ukraine_pipeline.classify_coin_photos import Verdict, classify
from app.ukraine_pipeline.roll_photos import match_candidates, oblast_name
from app.ukraine_recon import ua_coins
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError

ROLES = ("obverse", "reverse")
OFFICIAL_SOURCES = (MediaSource.NBU, MediaSource.UA_COINS, MediaSource.MANUAL)
YES = frozenset({"y", "yes", "1", "true", "+", "так"})
CSV_COLUMNS = (
    "decision",
    "itemId",
    "title",
    "year",
    "verdict",
    "circularity",
    "aspect",
    "fill",
    "replacementUrl",
    "note",
)
EXIT_OK = 0
EXIT_USAGE = 2


@dataclass
class ItemVerdict:
    item_id: int
    title: str
    year: int
    is_coin: bool
    worst_circularity: float
    worst_aspect: float
    worst_fill: float
    note: str


@dataclass
class ScanOutcome:
    items: list[ItemVerdict] = field(default_factory=list)
    without_photo: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        packaging = [item for item in self.items if not item.is_coin]
        return {
            "scanned": len(self.items),
            "packaging": len(packaging),
            "coin": len(self.items) - len(packaging),
            "withoutPhoto": len(self.without_photo),
            "failed": len(self.failed),
        }


@dataclass
class ApplyOutcome:
    replaced: list[dict[str, Any]] = field(default_factory=list)
    skipped_no_url: list[int] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "replaced": len(self.replaced),
            "skippedNoReplacementUrl": len(self.skipped_no_url),
            "failed": len(self.failed),
        }


# --------------------------------------------------------------------- scan
async def _candidate_items(session: AsyncSession, *, country_id: int) -> list[Any]:
    """Every shared, active Ukrainian record with an official photo, plus
    every "Ми сильні. Ми разом." record even without one — see the module
    docstring: this scan must never silently miss one of those nine (or a
    newly catalogued oblast) just because it has no stored photo yet."""
    with_photo = (
        select(CatalogItem.id)
        .join(MediaFile)
        .where(MediaFile.source.in_(OFFICIAL_SOURCES), MediaFile.storage_key.is_not(None))
    )
    rows = await session.execute(
        select(CatalogItem)
        .where(
            CatalogItem.country_id == country_id,
            CatalogItem.created_by.is_(None),
            CatalogItem.is_archived.is_(False),
            (
                CatalogItem.id.in_(with_photo)
                | CatalogItem.title_original.like("Ми сильні. Ми разом.%")
            ),
        )
        .order_by(CatalogItem.id)
    )
    return list(rows.scalars().all())


def _worst(verdicts: list[Verdict]) -> tuple[bool, float, float, float]:
    is_coin = all(v.is_coin for v in verdicts)
    return (
        is_coin,
        min((v.worst_circularity for v in verdicts), default=0.0),
        min((v.worst_aspect for v in verdicts), default=0.0),
        min((v.worst_fill for v in verdicts), default=0.0),
    )


async def scan(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    country_id: int,
    limit: int | None,
    log: Callable[[str], None],
) -> ScanOutcome:
    outcome = ScanOutcome()
    items = await _candidate_items(session, country_id=country_id)
    if limit is not None:
        items = items[:limit]
    for index, item in enumerate(items, start=1):
        rows = (
            (
                await session.execute(
                    select(MediaFile).where(
                        MediaFile.catalog_item_id == item.id,
                        MediaFile.source.in_(OFFICIAL_SOURCES),
                        MediaFile.storage_key.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            outcome.without_photo.append({"itemId": item.id, "title": item.title_original})
            continue
        verdicts: list[Verdict] = []
        try:
            for row in rows:
                assert row.storage_key is not None  # the query's own filter guarantees this
                payload = storage.get(row.storage_key)
                with tempfile.NamedTemporaryFile(suffix=".webp") as handle:
                    handle.write(payload)
                    handle.flush()
                    verdicts.append(classify(Path(handle.name)))
        except Exception as exc:  # a bad object must not stop the run
            outcome.failed.append(
                {"itemId": item.id, "title": item.title_original, "error": str(exc)}
            )
            continue
        is_coin, circularity, aspect, fill = _worst(verdicts)
        outcome.items.append(
            ItemVerdict(
                item_id=item.id,
                title=item.title_original,
                year=item.issue_year,
                is_coin=is_coin,
                worst_circularity=circularity,
                worst_aspect=aspect,
                worst_fill=fill,
                note="ok" if is_coin else "non-circular object in a stored photo",
            )
        )
        if index % 25 == 0 or index == len(items):
            log(f"scan {index}/{len(items)}")
    return outcome


def write_report_csv(path: Path, outcome: ScanOutcome, replacements: dict[int, str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        rows = 0
        for item in outcome.items:
            writer.writerow(
                {
                    "decision": "",
                    "itemId": item.item_id,
                    "title": item.title,
                    "year": item.year,
                    "verdict": "coin" if item.is_coin else "packaging",
                    "circularity": round(item.worst_circularity, 2),
                    "aspect": round(item.worst_aspect, 2),
                    "fill": round(item.worst_fill, 2),
                    "replacementUrl": replacements.get(item.item_id, ""),
                    "note": item.note,
                }
            )
            rows += 1
        for row in outcome.without_photo:
            writer.writerow(
                {
                    "decision": "",
                    "itemId": row["itemId"],
                    "title": row["title"],
                    "year": "",
                    "verdict": "no-photo",
                    "circularity": "",
                    "aspect": "",
                    "fill": "",
                    "replacementUrl": replacements.get(row["itemId"], ""),
                    "note": "no official photo stored yet",
                }
            )
            rows += 1
    return rows


def read_review_csv(path: Path) -> dict[int, str]:
    """{item id: replacement URL} for every row marked yes with a URL filled in."""
    chosen: dict[int, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() not in YES:
                continue
            url = (row.get("replacementUrl") or "").strip()
            if url:
                chosen[int(str(row["itemId"]).strip())] = url
    return chosen


def find_replacements(client: PoliteClient, items: list[Any]) -> dict[int, str]:
    """{item id: show-regular-ua URL} for every "Ми сильні" title the listing carries."""
    candidates = [
        (item.id, item.title_original) for item in items if oblast_name(item.title_original)
    ]
    if not candidates:
        return {}
    result = client.get(ua_coins.regular_ua_listing_url())
    if not result.ok:
        return {}
    listing = ua_coins.parse_regular_ua_listing(result.text)
    return {c.item_id: c.url for c in match_candidates(candidates, listing)}


# -------------------------------------------------------------------- apply
async def _replace_photo(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    item_id: int,
    url: str,
) -> dict[str, Any]:
    result = client.get(url)
    if not result.ok:
        message = f"HTTP {result.status} for {url}"
        raise SourceUnreachableError(url.split("/")[2], message)
    images = ua_coins.parse_regular_ua_detail(result.text)
    urls = {"obverse": images.obverse, "reverse": images.reverse}
    if not any(urls.values()):
        message = f"no obverse/reverse photograph found on {url}"
        raise ValueError(message)

    old_rows = (
        (
            await session.execute(
                select(MediaFile).where(
                    MediaFile.catalog_item_id == item_id,
                    MediaFile.source.in_(OFFICIAL_SOURCES),
                    MediaFile.role.in_([MediaRole(role) for role in ROLES]),
                )
            )
        )
        .scalars()
        .all()
    )
    old_keys = [key for row in old_rows for key in (row.variants or {}).values()]

    stored: list[str] = []
    for role, side_url in urls.items():
        if not side_url:
            continue
        _result, payload = client.get_range(side_url, 12 * 1024 * 1024)
        if payload is None:
            continue
        processed = process_image(payload)
        base = catalog_base(item_id, role, processed.sha256[:16])
        keys = {side: variant_key(base, side) for side in processed.variants}
        for side, key in keys.items():
            storage.put(key, processed.variants[side], processed.mime_type)
        session.add(
            MediaFile(
                catalog_item_id=item_id,
                owner_id=None,
                role=MediaRole(role),
                source=MediaSource.UA_COINS,
                license="ua-coins.info, © 2015-2026, used with attribution",
                attribution="ua-coins.info",
                storage_key=primary_key_of(keys),
                thumbnail_key=preview_key_of(keys),
                variants=stored_variants(keys),
                external_url=side_url,
                mime_type=processed.mime_type,
                width=processed.width,
                height=processed.height,
                size_bytes=processed.total_bytes,
                sha256=processed.sha256,
            )
        )
        stored.append(role)

    for row in old_rows:
        await session.delete(row)
    if old_keys:
        storage.delete_many(old_keys)
    await session.flush()
    return {
        "itemId": item_id,
        "url": url,
        "rolesReplaced": stored,
        "oldPhotosRemoved": len(old_rows),
    }


async def apply_replacements(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    decisions: dict[int, str],
    dry_run: bool,
    log: Callable[[str], None],
) -> ApplyOutcome:
    outcome = ApplyOutcome()
    for item_id, url in decisions.items():
        if dry_run:
            outcome.replaced.append({"itemId": item_id, "url": url})
            continue
        try:
            row = await _replace_photo(
                session, storage=storage, client=client, item_id=item_id, url=url
            )
            outcome.replaced.append(row)
            await session.commit()
        except Exception as exc:  # one bad replacement must not stop the run
            await session.rollback()
            outcome.failed.append({"itemId": item_id, "url": url, "error": str(exc)})
        log(f"apply {len(outcome.replaced) + len(outcome.failed)}/{len(decisions)}")
    return outcome


# ------------------------------------------------------------------------ cli
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="where the scan writes its review CSV")
    parser.add_argument("--report", type=Path, help="JSON report")
    parser.add_argument("--cache-dir", type=Path, help="disk cache for the ua-coins.info fetches")
    parser.add_argument("--apply", action="store_true", help="write to the database and to storage")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit form of the default: report, change nothing",
    )
    parser.add_argument("--apply-review", type=Path, dest="review_in", help="a reviewed scan CSV")
    parser.add_argument("--limit", type=int, help="stop the scan after N catalog items")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace, log: Callable[[str], None]) -> int:
    from app.core.config import get_settings
    from app.core.storage import build_s3_client
    from app.db.session import dispose_engine, get_session_factory

    settings = get_settings()
    storage = ObjectStorage(build_s3_client(settings), settings.s3_bucket)
    dry_run = not args.apply
    report: dict[str, Any] = {"dryRun": dry_run}

    with PoliteClient(cache_dir=args.cache_dir) as client:
        try:
            async with get_session_factory()() as session:
                country_id = await ukraine_country_id(session)
                if country_id is None:
                    print("no Ukraine in the countries table", file=sys.stderr)
                    return EXIT_USAGE

                if args.review_in is not None:
                    decisions = read_review_csv(args.review_in)
                    log(f"{len(decisions)} rows marked yes with a replacement URL")
                    apply_outcome = await apply_replacements(
                        session,
                        storage=storage,
                        client=client,
                        decisions=decisions,
                        dry_run=dry_run,
                        log=log,
                    )
                    report["apply"] = apply_outcome.summary()
                    report["replaced"] = apply_outcome.replaced
                    report["failed"] = apply_outcome.failed
                else:
                    outcome = await scan(
                        session, storage=storage, country_id=country_id, limit=args.limit, log=log
                    )
                    items = await _candidate_items(session, country_id=country_id)
                    replacements = find_replacements(client, items)
                    report["scan"] = outcome.summary()
                    report["packaging"] = [
                        {
                            "itemId": i.item_id,
                            "title": i.title,
                            "replacementUrl": replacements.get(i.item_id, ""),
                        }
                        for i in outcome.items
                        if not i.is_coin
                    ]
                    if args.out is not None:
                        rows = write_report_csv(args.out, outcome, replacements)
                        log(f"{rows} rows written to {args.out}")
        finally:
            await dispose_engine()

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report.get("scan") or report.get("apply") or {}, indent=2, ensure_ascii=False))
    return EXIT_OK


class Progress:
    def __call__(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.apply and args.dry_run:
        print("--apply and --dry-run contradict each other", file=sys.stderr)
        return EXIT_USAGE
    if args.review_in is not None and not args.review_in.exists():
        print(f"review file not found: {args.review_in}", file=sys.stderr)
        return EXIT_USAGE
    return asyncio.run(_run(args, Progress()))


if __name__ == "__main__":
    raise SystemExit(main())
