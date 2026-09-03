"""Reconnaissance of the Ukrainian coin sources against our catalogue.

Stage 4.5, part A (docs/05-integrations.md, "Разведка"). Read-only: nothing
is written to the database or to object storage; the only outputs are the
report and the page cache.

    python scripts/recon_ukraine.py --report /reports/recon.json \
        --cache-dir /reports/ukraine-cache

The parsers live in app/ukraine_recon/; this file is the command line.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import struct
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from app.ukraine_recon import nbu, triangulate, ua_coins, wikipedia
from app.ukraine_recon.catalog import CatalogSnapshot
from app.ukraine_recon.http import FetchResult, PoliteClient, SourceUnreachableError
from app.ukraine_recon.models import (
    SOURCE_NBU,
    SOURCE_UA_COINS,
    SOURCE_WIKIPEDIA,
    SourceRecord,
    records_to_json,
)
from app.ukraine_recon.report import ReconReport

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SOURCE = 3
EXIT_FAILED = 5

DEFAULT_REPORT = Path(__file__).resolve().parent / "recon-report.json"
FIRST_YEAR = 1992
MODE_AUTO = "auto"
MODE_LIVE = "live"
MODE_WAYBACK = "wayback"
IMAGE_HEADER_BYTES = 4096

UA_COINS_ROBOTS = f"{ua_coins.BASE_URL}/robots.txt"
UA_COINS_TERMS = f"{ua_coins.BASE_URL}/ua/terms"
NBU_ROBOTS = f"{nbu.BASE_URL}/robots.txt"
NBU_TERMS = f"{nbu.BASE_URL}/ua/useterms"
WIKI_ROBOTS = "https://uk.wikipedia.org/robots.txt"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconnaissance of the Ukrainian coin sources.")
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT, help="where to write the JSON"
    )
    parser.add_argument("--cache-dir", type=Path, help="disk cache for fetched pages")
    parser.add_argument(
        "--limit-years", type=int, help="only the N most recent years (a trial run)"
    )
    parser.add_argument(
        "--ua-coins",
        choices=(MODE_AUTO, MODE_LIVE, MODE_WAYBACK),
        default=MODE_AUTO,
        help="live site, the Wayback Machine copy, or live with a Wayback fallback",
    )
    parser.add_argument("--skip-catalog", action="store_true", help="do not read the database")
    parser.add_argument("--catalog-from", type=Path, help="our catalogue from an earlier export")
    parser.add_argument("--catalog-export", type=Path, help="write our catalogue as JSON")
    parser.add_argument("--skip-images", action="store_true", help="no HEAD requests for images")
    parser.add_argument("--image-sample", type=int, default=50, help="matched coins to probe")
    parser.add_argument(
        "--pause", type=float, default=0.45, help="seconds between requests per host"
    )
    parser.add_argument("--series-map", type=Path, default=triangulate.SERIES_MAP_PATH)
    return parser.parse_args(argv)


class Progress:
    def __init__(self, stream: Any = sys.stderr) -> None:
        self.stream = stream

    def __call__(self, message: str) -> None:
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        print(f"[{stamp}] {message}", file=self.stream, flush=True)


# ------------------------------------------------------------------ ua-coins
def fetch_ua_coins(
    client: PoliteClient, report: ReconReport, mode: str, log: Progress
) -> tuple[list[SourceRecord], list[ua_coins.SeriesCount], dict[str, Any]]:
    """The all-years table in both locales, the series page, the plan page."""
    access = "live"
    fetch: Callable[[str], FetchResult] = client.get
    if mode != MODE_LIVE:
        try:
            probe = client.get(ua_coins.catalog_url("all")) if mode == MODE_AUTO else None
        except SourceUnreachableError as exc:
            report.warn(f"ua-coins.info unreachable ({exc.reason}); using the Wayback Machine copy")
            probe = None
        if probe is None or not probe.ok:
            access = "wayback"
            fetch = client.get_archived
            if mode == MODE_AUTO and probe is not None:
                report.warn(
                    f"ua-coins.info answered HTTP {probe.status}; using the Wayback Machine copy"
                )

    def page(url: str, label: str) -> FetchResult | None:
        try:
            result = fetch(url)
        except SourceUnreachableError as exc:
            report.warn(f"ua-coins {label}: {exc}")
            return None
        if not result.ok:
            report.warn(f"ua-coins {label}: HTTP {result.status} for {url}")
            return None
        stamp = f" (archived {result.archived_at})" if result.archived_at else ""
        log(f"ua-coins {label}: {len(result.text)} bytes{stamp}")
        return result

    info: dict[str, Any] = {"access": access, "pages": {}}
    all_uk = page(ua_coins.catalog_url("all", ua_coins.LOCALE_UK), "catalog uk")
    rows_uk = ua_coins.parse_catalog_page(all_uk.text) if all_uk else []
    info["pages"]["catalogUk"] = {
        "url": ua_coins.catalog_url("all", ua_coins.LOCALE_UK),
        "rows": len(rows_uk),
        "archivedAt": all_uk.archived_at if all_uk else None,
    }
    if not rows_uk:
        # The all-years page is the shortcut; the per-year pages are the
        # documented route and the fallback.
        report.warn("ua-coins: the all-years page gave no rows, falling back to year pages")
        for year in range(FIRST_YEAR, date.today().year + 1):
            result = page(ua_coins.catalog_url(year, ua_coins.LOCALE_UK), f"catalog uk {year}")
            if result:
                rows_uk.extend(ua_coins.parse_catalog_page(result.text))
    all_ru = page(ua_coins.catalog_url("all", ua_coins.LOCALE_RU), "catalog ru")
    rows_ru = ua_coins.parse_catalog_page(all_ru.text) if all_ru else []
    info["pages"]["catalogRu"] = {
        "url": ua_coins.catalog_url("all", ua_coins.LOCALE_RU),
        "rows": len(rows_ru),
        "archivedAt": all_ru.archived_at if all_ru else None,
    }
    records = ua_coins.rows_to_records(rows_uk, rows_ru)

    series: list[ua_coins.SeriesCount] = []
    for locale in (ua_coins.LOCALE_EN, ua_coins.LOCALE_UK):
        result = page(ua_coins.categories_url(locale), f"categories {locale or 'ru'}")
        if result:
            parsed = ua_coins.parse_categories_page(result.text)
            info["pages"][f"categories_{locale or 'ru'}"] = {
                "url": ua_coins.categories_url(locale),
                "rows": len(parsed),
                "archivedAt": result.archived_at,
            }
            if parsed and not series:
                series = parsed
    plan = page(ua_coins.plan_url(), "nbu plan")
    if plan:
        years = sorted(set(re.findall(r"(20\d\d)\s*рік", plan.text)))
        info["pages"]["plan"] = {
            "url": ua_coins.plan_url(),
            "yearsListed": years,
            "archivedAt": plan.archived_at,
        }
    info["imageVariants"] = {
        name: ua_coins.image_url(0, "obverse", name).replace("/0_", "/{id}_")
        for name in ua_coins.IMAGE_VARIANTS
    }
    return records, series, info


# ----------------------------------------------------------------------- nbu
def fetch_nbu(
    client: PoliteClient, report: ReconReport, log: Progress, *, since_year: int | None
) -> tuple[list[SourceRecord], list[nbu.NbuCard], dict[str, Any]]:
    info: dict[str, Any] = {
        "access": "live",
        "searchUrl": nbu.SEARCH_URL,
        "pageSize": nbu.PAGE_SIZE,
    }
    catalog_page = client.get(nbu.CATALOG_URL)
    if catalog_page.ok:
        info["seriesFilter"] = nbu.parse_series_options(catalog_page.text)
    else:
        report.warn(f"nbu catalogue page: HTTP {catalog_page.status}")
    date_from = f"01.01.{since_year}" if since_year else None
    cards: list[nbu.NbuCard] = []
    page_number = 1
    page_count: int | None = None
    total: int | None = None
    while page_count is None or page_number <= page_count:
        result = client.post(nbu.SEARCH_URL, nbu.search_form(page_number, date_from=date_from))
        if not result.ok:
            report.warn(f"nbu search page {page_number}: HTTP {result.status}")
            break
        parsed = nbu.parse_search_page(result.text)
        if page_count is None:
            page_count = parsed.page_count or 1
            total = parsed.total
            log(f"nbu: {total} results, {page_count} pages of {nbu.PAGE_SIZE}")
        if not parsed.cards:
            report.warn(f"nbu search page {page_number}: no cards parsed")
            break
        cards.extend(parsed.cards)
        page_number += 1
    info["total"] = total
    info["pages"] = page_count
    info["fieldCoverage"] = nbu.field_coverage(cards)
    records = [nbu.card_to_record(card) for card in cards]
    # Souvenir products are a separate category on the NBU site; the count is
    # worth knowing because ua-coins mixes them into its table.
    souvenirs = client.post(
        nbu.SEARCH_URL, nbu.search_form(1, per_page=5, category=nbu.CATEGORY_SOUVENIR)
    )
    if souvenirs.ok:
        info["souvenirTotal"] = nbu.parse_search_page(souvenirs.text).total
    return records, cards, info


# ----------------------------------------------------------------- wikipedia
def fetch_wikipedia(
    client: PoliteClient, report: ReconReport, log: Progress
) -> tuple[list[SourceRecord], list[wikipedia.MintSet], dict[str, Any]]:
    info: dict[str, Any] = {"access": "live", "pages": {}}
    records: list[SourceRecord] = []
    for page in (wikipedia.PAGE_PRECIOUS, wikipedia.PAGE_BASE):
        result = client.get(wikipedia.page_url(page))
        if not result.ok:
            report.warn(f"wikipedia {page}: HTTP {result.status}")
            continue
        parsed = wikipedia.parse_list_page(result.text, page)
        groups: dict[str, int] = {}
        for record in parsed:
            groups[record.metal or "?"] = groups.get(record.metal or "?", 0) + 1
        info["pages"][page] = {
            "url": wikipedia.page_url(page),
            "rows": len(parsed),
            "groups": groups,
        }
        log(f"wikipedia {page[:40]}…: {len(parsed)} rows {groups}")
        records.extend(parsed)
    sets: list[wikipedia.MintSet] = []
    result = client.get(wikipedia.page_url(wikipedia.PAGE_HRYVNIA))
    if result.ok:
        sets = wikipedia.parse_sets(result.text)
        info["pages"][wikipedia.PAGE_HRYVNIA] = {
            "url": wikipedia.page_url(wikipedia.PAGE_HRYVNIA),
            "sets": len(sets),
        }
    else:
        report.warn(f"wikipedia {wikipedia.PAGE_HRYVNIA}: HTTP {result.status}")
    return records, sets, info


# -------------------------------------------------------------------- images
def _image_dimensions(head: bytes) -> tuple[int, int] | None:
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        width, height = struct.unpack(">II", head[16:24])
        return width, height
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and len(head) >= 30:
        chunk = head[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(head[24:27], "little")
            height = 1 + int.from_bytes(head[27:30], "little")
            return width, height
        if chunk == b"VP8L":
            bits = int.from_bytes(head[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8 ":
            width = int.from_bytes(head[26:28], "little") & 0x3FFF
            height = int.from_bytes(head[28:30], "little") & 0x3FFF
            return width, height
    if head[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 < len(head):
            if head[offset] != 0xFF:
                offset += 1
                continue
            marker = head[offset + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack(">HH", head[offset + 5 : offset + 9])
                return width, height
            length = struct.unpack(">H", head[offset + 2 : offset + 4])[0]
            offset += 2 + length
    return None


def probe_images(
    client: PoliteClient,
    report: ReconReport,
    log: Progress,
    *,
    ua_records: list[SourceRecord],
    ua_access: str,
    nbu_records: list[SourceRecord],
    matched_ua_ids: list[str],
    sample_size: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    by_id = {record.source_id: record for record in ua_records}
    ids = [i for i in matched_ua_ids if i in by_id][:sample_size] or [
        r.source_id for r in ua_records
    ][:sample_size]
    if ua_access != "live":
        result[SOURCE_UA_COINS] = {
            "note": "ua-coins.info unreachable from this host; image HEADs skipped. "
            "Archive evidence: /images/coins/{id}_{side}.jpg (5-60 KB), "
            "small|middle|big/{id}_{side}.webp and big/{id}_{side}.png exist for recent coins.",
            "sampleIds": ids,
            "variants": {},
        }
    else:
        variants: dict[str, dict[str, Any]] = {}
        large_sample = ids[: max(1, len(ids) // 4)]
        for name in ua_coins.IMAGE_VARIANTS:
            sides = ("obverse", "reverse") if name == "small_webp" else ("obverse",)
            subject = ids if name in ("small_webp", "legacy_jpg") else large_sample
            variants[name] = _probe_variant(
                client,
                [(ua_coins.image_url(int(i), side, name)) for i in subject for side in sides],
            )
            log(f"ua-coins images {name}: {variants[name]['ok']}/{variants[name]['checked']}")
        result[SOURCE_UA_COINS] = {"sampleIds": ids, "variants": variants}

    nbu_sample = [r for r in nbu_records if r.image_urls][: max(5, sample_size // 5)]
    nbu_variants = {
        "big_png": _probe_variant(client, [r.image_urls[0] for r in nbu_sample]),
        "thumbnail_jpg": _probe_variant(
            client, [t for r in nbu_sample for t in r.extra.get("thumbnails", [])[:1]]
        ),
    }
    log(f"nbu images: big {nbu_variants['big_png']['ok']}/{nbu_variants['big_png']['checked']}")
    result[SOURCE_NBU] = {
        "sampleIds": [r.source_id for r in nbu_sample],
        "variants": nbu_variants,
        "urlTemplates": {
            "thumbnail": f"{nbu.BASE_URL}/media/coins/{{id}}/avers.jpg | revers.jpg",
            "full": (
                f"{nbu.BASE_URL}/files/coins_images/{{code}}a.png | {{code}}r.png"
                " (+ a0/r0 extra views, u.pdf booklet)"
            ),
        },
    }
    return result


def _probe_variant(client: PoliteClient, urls: list[str]) -> dict[str, Any]:
    sizes: list[int] = []
    ok = 0
    statuses: dict[str, int] = {}
    dimensions: tuple[int, int] | None = None
    for position, url in enumerate(urls):
        try:
            head = client.head(url)
        except SourceUnreachableError:
            statuses["unreachable"] = statuses.get("unreachable", 0) + 1
            continue
        statuses[str(head.status)] = statuses.get(str(head.status), 0) + 1
        if head.ok:
            ok += 1
            length = head.headers.get("content-length")
            if length and length.isdigit():
                sizes.append(int(length))
            if dimensions is None and position < 3:
                try:
                    _, body = client.get_range(url, IMAGE_HEADER_BYTES)
                    dimensions = _image_dimensions(body)
                except SourceUnreachableError:
                    pass
    return {
        "checked": len(urls),
        "ok": ok,
        "statuses": statuses,
        "bytesMedian": int(median(sizes)) if sizes else None,
        "bytesMin": min(sizes) if sizes else None,
        "bytesMax": max(sizes) if sizes else None,
        "dimensions": list(dimensions) if dimensions else None,
        "example": urls[0] if urls else None,
    }


# -------------------------------------------------------------------- rights
def fetch_rights(client: PoliteClient, report: ReconReport, ua_access: str) -> dict[str, Any]:
    rights: dict[str, Any] = {}

    def robots(url: str, archived: bool) -> str:
        try:
            result = client.get_archived(url) if archived else client.get(url)
        except SourceUnreachableError as exc:
            return f"unreachable: {exc.reason}"
        if not result.ok:
            return f"HTTP {result.status}"
        lines = [
            line.strip()
            for line in result.text.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        return " | ".join(lines[:12])

    def quotes(url: str, archived: bool, patterns: list[str]) -> list[str]:
        try:
            result = client.get_archived(url) if archived else client.get(url)
        except SourceUnreachableError as exc:
            return [f"unreachable: {exc.reason}"]
        if not result.ok:
            return [f"HTTP {result.status}"]
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", result.text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        found = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                start = max(0, match.start() - 20)
                found.append(text[start : match.end() + 220].strip())
                break
        return found

    archived = ua_access != "live"
    rights["ua-coins"] = {
        "robots": robots(UA_COINS_ROBOTS, archived),
        "termsUrl": UA_COINS_TERMS,
        "quotes": quotes(
            UA_COINS_TERMS,
            archived,
            [r"Умови використання", r"Відмова від відповідальності", r"Copyright"],
        ),
        "source": "wayback" if archived else "live",
    }
    rights["nbu"] = {
        "robots": robots(NBU_ROBOTS, False),
        "termsUrl": NBU_TERMS,
        "quotes": quotes(
            NBU_TERMS,
            False,
            [
                r"Національний банк України – власник доменного імені",
                r"Матеріали сайту можуть бути використані",
            ],
        ),
    }
    rights["wikipedia"] = {
        "robots": robots(WIKI_ROBOTS, False)[:300],
        "termsUrl": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        "quotes": [
            "Text is available under the Creative Commons Attribution-ShareAlike License 4.0;"
            " images carry their own licence on the file page."
        ],
    }
    return rights


# --------------------------------------------------------------------- main
async def _load_catalog_from_db() -> CatalogSnapshot:
    from app.db.session import dispose_engine, get_session_factory
    from app.ukraine_recon.catalog import load_catalog

    try:
        async with get_session_factory()() as session:
            return await load_catalog(session)
    finally:
        await dispose_engine()


def _limit(records: list[SourceRecord], since_year: int | None) -> list[SourceRecord]:
    if since_year is None:
        return records
    return [record for record in records if record.year is None or record.year >= since_year]


def run(args: argparse.Namespace) -> int:
    log = Progress()
    report = ReconReport()
    report.options = {
        "limitYears": args.limit_years,
        "uaCoins": args.ua_coins,
        "skipCatalog": args.skip_catalog,
        "catalogFrom": str(args.catalog_from) if args.catalog_from else None,
        "skipImages": args.skip_images,
        "imageSample": args.image_sample,
        "cacheDir": str(args.cache_dir) if args.cache_dir else None,
    }
    since_year = date.today().year - args.limit_years + 1 if args.limit_years else None

    with PoliteClient(cache_dir=args.cache_dir, pause_seconds=args.pause) as client:
        # Step 1: the three indexes.
        ua_records, ua_series, ua_info = fetch_ua_coins(client, report, args.ua_coins, log)
        ua_records = _limit(ua_records, since_year)
        report.sources[SOURCE_UA_COINS] = {
            **ua_info,
            "records": len(ua_records),
            "summary": ua_coins.catalog_summary(ua_records),
            "series": [s.__dict__ for s in ua_series],
        }
        try:
            nbu_records, _nbu_cards, nbu_info = fetch_nbu(
                client, report, log, since_year=since_year
            )
        except SourceUnreachableError as exc:
            report.warn(f"nbu unreachable: {exc}")
            nbu_records, _nbu_cards, nbu_info = [], [], {"access": "unreachable"}
        report.sources[SOURCE_NBU] = {
            **nbu_info,
            "records": len(nbu_records),
            "summary": {
                "coins": sum(1 for r in nbu_records if r.kind == "coin"),
                "sets": sum(1 for r in nbu_records if r.kind == "set"),
                "souvenirs": sum(1 for r in nbu_records if r.kind == "souvenir"),
                "withSeries": sum(1 for r in nbu_records if r.series),
                "withMintage": sum(1 for r in nbu_records if r.mintage),
            },
        }
        report.nbu_sample = [r.to_dict() for r in nbu_records[:30]]
        try:
            wiki_records, wiki_sets, wiki_info = fetch_wikipedia(client, report, log)
        except SourceUnreachableError as exc:
            report.warn(f"wikipedia unreachable: {exc}")
            wiki_records, wiki_sets, wiki_info = [], [], {"access": "unreachable"}
        wiki_records = _limit(wiki_records, since_year)
        report.sources[SOURCE_WIKIPEDIA] = {
            **wiki_info,
            "records": len(wiki_records),
            "summary": {
                "silver": sum(1 for r in wiki_records if r.metal == wikipedia.GROUP_SILVER),
                "gold": sum(1 for r in wiki_records if r.metal == wikipedia.GROUP_GOLD),
                "bimetal": sum(1 for r in wiki_records if r.metal == wikipedia.GROUP_BIMETAL),
                "base": sum(1 for r in wiki_records if r.metal == wikipedia.GROUP_BASE),
                "sets": len(wiki_sets),
            },
            "mintSets": [s.__dict__ for s in wiki_sets],
        }
        sources = {
            SOURCE_NBU: nbu_records,
            SOURCE_UA_COINS: ua_records,
            SOURCE_WIKIPEDIA: wiki_records,
        }
        for name, records in sources.items():
            promoted = triangulate.promote_packaged_coins(records)
            if promoted:
                report.sources[name]["packagedOnlyCoins"] = promoted
                log(f"{name}: {promoted} packaged-only rows counted as coins")
        if not any(sources.values()):
            print("No source could be read; nothing to report.", file=sys.stderr)
            return EXIT_SOURCE
        if args.report.parent:
            indexes_dir = args.report.parent / "recon-indexes"
            indexes_dir.mkdir(parents=True, exist_ok=True)
            for name, records in sources.items():
                path = indexes_dir / f"{name}.json"
                path.write_text(
                    __import__("json").dumps(
                        records_to_json(records), ensure_ascii=False, indent=1
                    ),
                    encoding="utf-8",
                )
            report.options["indexesDir"] = str(indexes_dir)

        # Step 2: our catalogue.
        snapshot: CatalogSnapshot | None = None
        if args.catalog_from:
            snapshot = CatalogSnapshot.read(args.catalog_from)
            log(f"catalog: {len(snapshot.items)} items from {args.catalog_from}")
        elif not args.skip_catalog:
            snapshot = asyncio.run(_load_catalog_from_db())
            log(
                f"catalog: {len(snapshot.items)} items, {len(snapshot.series)} series"
                " from the database"
            )
            if args.catalog_export:
                snapshot.write(args.catalog_export)
        if snapshot is not None and since_year is not None:
            snapshot.items = [item for item in snapshot.items if item.issue_year >= since_year]
        items = snapshot.items if snapshot else []
        if snapshot is not None:
            report.catalog = triangulate.catalog_overview(snapshot)

        # Step 3: triangulation.
        clusters = triangulate.cluster_records(sources)
        log(f"clusters: {len(clusters)} across {sum(len(v) for v in sources.values())} records")
        report.year_table = triangulate.build_year_table(sources, clusters, items)
        report.series_table = triangulate.build_series_table(
            ua_series,
            nbu_records,
            snapshot.series if snapshot else [],
            triangulate.load_series_map(args.series_map),
        )
        result = triangulate.match_catalog(items, sources)
        by_item = result.by_item()
        items_matched = {
            name: len({m.item_id for m in result.matches if m.source == name}) for name in sources
        }
        report.matching = {
            "counts": result.counts(),
            "itemsMatched": items_matched,
            "itemsMatchedAny": len(by_item),
            "itemsMatchedAll": sum(
                1 for matches in by_item.values() if {m.source for m in matches} == set(sources)
            ),
            "examples": result.examples(),
            "oneToMany": len(result.one_to_many),
            "manyToOne": len(result.many_to_one),
            "oneToManyList": result.one_to_many,
            "manyToOneList": result.many_to_one,
            "strategies": {
                "A": "source_url on ua-coins.info",
                "B": "denomination + year + normalised title (uk or ru), plus the prefix rule",
                "C": "rapidfuzz token_sort_ratio >= 85, same denomination and year",
                "C1": "as C with the year off by one",
                "D": "catalogue number: not applicable, no source exposes one",
            },
        }
        report.unmatched_ours = triangulate.unmatched_items(items, result)
        report.candidates = triangulate.candidate_additions(clusters, result)
        log(
            f"matching: {len(result.matches)} matches, {len(by_item)} items matched, "
            f"{len(report.unmatched_ours)} unmatched, {len(report.candidates)} candidates"
        )

        # Step 4: images.
        if not args.skip_images:
            matched_ua_ids = [m.source_id for m in result.matches if m.source == SOURCE_UA_COINS]
            report.images = probe_images(
                client,
                report,
                log,
                ua_records=ua_records,
                ua_access=ua_info.get("access", "live"),
                nbu_records=nbu_records,
                matched_ua_ids=matched_ua_ids,
                sample_size=args.image_sample,
            )

        # Step 5 and 6: prices and titles.
        report.prices = triangulate.compare_prices(
            items, result, ua_records, sample_size=args.image_sample
        )
        report.titles = triangulate.compare_titles(clusters, items, result)

        # Step 7: rights.
        report.rights = fetch_rights(client, report, ua_info.get("access", "live"))
        report.http = {
            "requests": client.requests_made,
            "cacheHits": client.cache_hits,
            "deadHosts": client.dead_hosts,
        }

    report.assumptions = [
        "Only rows classified as coins count in the year table; sets and souvenir "
        "packagings are listed separately.",
        "A Wayback Machine copy of ua-coins.info stands in for the live site when the site "
        "does not answer.",
        "Our catalogue side is the shared catalogue only (created_by IS NULL), country Ukraine.",
    ]
    report.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
    report.write(args.report)
    for line in report.summary_lines():
        print(line)
    print(f"\nreport written to {args.report}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.catalog_from and not args.catalog_from.exists():
        print(f"catalog export not found: {args.catalog_from}", file=sys.stderr)
        return EXIT_USAGE
    try:
        return run(args)
    except SourceUnreachableError as exc:
        print(f"Source unreachable: {exc}", file=sys.stderr)
        return EXIT_SOURCE


if __name__ == "__main__":
    raise SystemExit(main())
