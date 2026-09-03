"""Triangulation: three sources against each other and against our catalogue.

A single source on Ukrainian coins is never complete. A coin is trusted
where the sources agree, and a coin we lack is a candidate only when at
least two of them list it.

Matching strategies for our items, applied in order and counted once per
item and source (an item matched by A is not counted again by B):

    A   a ua-coins.info reference we already hold: the source key, the URL
        of the latest price snapshot or a price source link (ua-coins only)
    B   exact key: denomination + year + normalised title, plus the legacy
        prefix rule (one title is the other plus a space and more)
    C   fuzzy title (rapidfuzz, threshold 85) with denomination and year equal
    C1  the same with the year off by one: issue date and the year struck
        differ around New Year
    D   catalogue number — not applicable: none of the three sources exposes
        Krause or uCoin numbers, and Wikipedia's № is its own sequence
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from rapidfuzz import fuzz

from app.ukraine_recon.catalog import CatalogEntry, CatalogSnapshot, SeriesEntry
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA, SourceRecord
from app.ukraine_recon.normalize import (
    bare_title,
    match_key,
    normalize_title,
    strip_source_suffix,
    titles_equivalent,
)
from app.ukraine_recon.ua_coins import SeriesCount

STRATEGY_URL = "A"
STRATEGY_EXACT = "B"
STRATEGY_FUZZY = "C"
STRATEGY_FUZZY_ADJACENT_YEAR = "C1"
STRATEGY_CATALOG_NUMBER = "D"
STRATEGIES = (
    STRATEGY_URL,
    STRATEGY_EXACT,
    STRATEGY_FUZZY,
    STRATEGY_FUZZY_ADJACENT_YEAR,
    STRATEGY_CATALOG_NUMBER,
)

FUZZY_THRESHOLD = 85.0
CROSS_SOURCE_THRESHOLD = 88.0
TIE_MARGIN = 1.0
MAX_EXAMPLES = 10
MAX_DISPUTED_PER_YEAR = 15
COMMEMORATIVE_GROUPS = ("commemorative", "collector")

SERIES_MAP_PATH = Path(__file__).with_name("series_map.json")
_UA_COINS_ID_RE = re.compile(r"ua-coins\.info/(?:[a-z]{2}/)?list/(\d+)")


# ---------------------------------------------------------------- source index
def source_titles(record: SourceRecord) -> list[str]:
    titles = []
    for title in (record.title_uk, record.title_ru):
        if title:
            titles.append(bare_title(title))
    return titles


def promote_packaged_coins(records: list[SourceRecord]) -> int:
    """A packaged coin with no bare twin in the same source is the coin.

    Since 2022 the NBU catalogue lists base-metal issues only as "у сувенірному
    пакованні"; counting those as souvenirs would make the NBU look short of
    a dozen coins a year. ua-coins lists both rows, so its packaged row stays
    a souvenir.
    """
    bare_keys = {
        match_key(r.denomination, r.year, source_titles(r)[0])
        for r in records
        if r.kind == "coin" and source_titles(r)
    }
    promoted = 0
    for record in records:
        if record.kind != "souvenir" or not source_titles(record):
            continue
        key = match_key(record.denomination, record.year, source_titles(record)[0])
        if key not in bare_keys:
            record.kind = "coin"
            record.extra["packagedOnly"] = True
            bare_keys.add(key)
            promoted += 1
    return promoted


def record_keys(record: SourceRecord) -> list[str]:
    return [match_key(record.denomination, record.year, title) for title in source_titles(record)]


@dataclass
class SourceIndex:
    source: str
    records: list[SourceRecord]
    by_id: dict[str, SourceRecord] = field(default_factory=dict)
    by_key: dict[str, list[SourceRecord]] = field(default_factory=lambda: defaultdict(list))
    by_slot: dict[tuple[str, int | None], list[SourceRecord]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def __post_init__(self) -> None:
        for record in self.records:
            self.by_id[record.source_id] = record
            for key in record_keys(record):
                self.by_key[key].append(record)
            self.by_slot[_slot(record.denomination, record.year)].append(record)

    def candidates(self, denomination: Decimal | None, year: int | None) -> list[SourceRecord]:
        return self.by_slot.get(_slot(denomination, year), [])


def _slot(denomination: Decimal | None, year: int | None) -> tuple[str, int | None]:
    value = "?" if denomination is None else format(denomination.normalize(), "f")
    return value, year


def _prefer_coins(records: list[SourceRecord]) -> list[SourceRecord]:
    """A coin and its packaged twin score the same; the coin is the answer."""
    coins = [record for record in records if record.kind == "coin"]
    return coins or records


def _fuzzy_score(our_titles: list[str], record: SourceRecord) -> float:
    best = 0.0
    for ours in our_titles:
        for theirs in source_titles(record):
            score = fuzz.token_sort_ratio(ours, normalize_title(theirs))
            best = max(best, float(score))
    return best


# ------------------------------------------------------------------- matching
@dataclass
class Match:
    item_id: int
    source: str
    source_id: str
    strategy: str
    score: float
    our_title: str
    source_title: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "itemId": self.item_id,
            "source": self.source,
            "sourceId": self.source_id,
            "strategy": self.strategy,
            "score": round(self.score, 1),
            "ourTitle": self.our_title,
            "sourceTitle": self.source_title,
        }


@dataclass
class MatchResult:
    matches: list[Match] = field(default_factory=list)
    one_to_many: list[dict[str, Any]] = field(default_factory=list)
    many_to_one: list[dict[str, Any]] = field(default_factory=list)

    def matched_pairs(self) -> set[tuple[str, str]]:
        return {(match.source, match.source_id) for match in self.matches}

    def by_item(self) -> dict[int, list[Match]]:
        grouped: dict[int, list[Match]] = defaultdict(list)
        for match in self.matches:
            grouped[match.item_id].append(match)
        return grouped

    def counts(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {
            source: dict.fromkeys(STRATEGIES, 0)
            for source in (SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA)
        }
        for match in self.matches:
            counts[match.source][match.strategy] += 1
        return counts

    def examples(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        examples: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for match in self.matches:
            bucket = examples[match.source][match.strategy]
            if len(bucket) < MAX_EXAMPLES:
                bucket.append(match.to_dict())
        return {source: dict(strategies) for source, strategies in examples.items()}


def _match_url(item: CatalogEntry, index: SourceIndex) -> Match | None:
    if index.source != SOURCE_UA_COINS or not item.source_url:
        return None
    found = _UA_COINS_ID_RE.search(item.source_url)
    if found is None:
        return None
    record = index.by_id.get(found.group(1))
    if record is None:
        return None
    return Match(
        item.id,
        index.source,
        record.source_id,
        STRATEGY_URL,
        100.0,
        item.title_original,
        record.title_uk or record.title_ru or "",
    )


def _match_exact(item: CatalogEntry, index: SourceIndex) -> tuple[Match | None, list[SourceRecord]]:
    hits: list[SourceRecord] = []
    for key in item.match_keys():
        for record in index.by_key.get(key, []):
            if record not in hits:
                hits.append(record)
    if not hits:
        our_norms = [normalize_title(title) for title in item.titles]
        for record in index.candidates(item.denomination, item.issue_year):
            theirs = [normalize_title(title) for title in source_titles(record)]
            if any(titles_equivalent(a, b) for a in our_norms for b in theirs):
                hits.append(record)
    if not hits:
        return None, []
    hits = _prefer_coins(hits)
    record = hits[0]
    match = Match(
        item.id,
        index.source,
        record.source_id,
        STRATEGY_EXACT,
        100.0,
        item.title_original,
        record.title_uk or record.title_ru or "",
    )
    return match, hits


def _match_fuzzy(
    item: CatalogEntry, index: SourceIndex, *, year_offset: int
) -> tuple[Match | None, list[tuple[float, SourceRecord]]]:
    our_titles = [normalize_title(title) for title in item.titles]
    scored: list[tuple[float, SourceRecord]] = []
    years = [item.issue_year] if year_offset == 0 else [item.issue_year - 1, item.issue_year + 1]
    for year in years:
        for record in index.candidates(item.denomination, year):
            score = _fuzzy_score(our_titles, record)
            if score >= FUZZY_THRESHOLD:
                scored.append((score, record))
    if not scored:
        return None, []
    scored.sort(key=lambda pair: -pair[0])
    best_score = scored[0][0]
    ties = _prefer_coins([record for score, record in scored if best_score - score <= TIE_MARGIN])
    best = ties[0]
    strategy = STRATEGY_FUZZY if year_offset == 0 else STRATEGY_FUZZY_ADJACENT_YEAR
    match = Match(
        item.id,
        index.source,
        best.source_id,
        strategy,
        best_score,
        item.title_original,
        best.title_uk or best.title_ru or "",
    )
    return match, [(score, record) for score, record in scored if record in ties]


def match_catalog(items: list[CatalogEntry], sources: dict[str, list[SourceRecord]]) -> MatchResult:
    result = MatchResult()
    indexes = {name: SourceIndex(name, records) for name, records in sources.items()}
    for item in items:
        for name, index in indexes.items():
            match = _match_url(item, index)
            if match is None:
                match, hits = _match_exact(item, index)
                if len(hits) > 1:
                    result.one_to_many.append(
                        {
                            "itemId": item.id,
                            "ourTitle": item.title_original,
                            "source": name,
                            "strategy": STRATEGY_EXACT,
                            "candidates": [
                                {"sourceId": hit.source_id, "title": hit.title_uk or hit.title_ru}
                                for hit in hits
                            ],
                        }
                    )
            if match is None:
                match, ties = _match_fuzzy(item, index, year_offset=0)
                if match is None:
                    match, ties = _match_fuzzy(item, index, year_offset=1)
                if len(ties) > 1:
                    result.one_to_many.append(
                        {
                            "itemId": item.id,
                            "ourTitle": item.title_original,
                            "source": name,
                            "strategy": match.strategy if match else STRATEGY_FUZZY,
                            "candidates": [
                                {
                                    "sourceId": record.source_id,
                                    "title": record.title_uk or record.title_ru,
                                    "score": round(score, 1),
                                }
                                for score, record in ties
                            ],
                        }
                    )
                    match = None
            if match is not None:
                result.matches.append(match)

    grouped: dict[tuple[str, str], list[Match]] = defaultdict(list)
    for match in result.matches:
        grouped[(match.source, match.source_id)].append(match)
    for (source, source_id), matches in grouped.items():
        if len(matches) > 1:
            result.many_to_one.append(
                {
                    "source": source,
                    "sourceId": source_id,
                    "sourceTitle": matches[0].source_title,
                    "items": [
                        {"itemId": m.item_id, "ourTitle": m.our_title, "strategy": m.strategy}
                        for m in matches
                    ],
                }
            )
    return result


# ------------------------------------------------------------ cross-source
@dataclass
class Cluster:
    records: list[SourceRecord]

    @property
    def sources(self) -> set[str]:
        return {record.source for record in self.records}

    @property
    def year(self) -> int | None:
        for record in self.records:
            if record.year is not None:
                return record.year
        return None

    @property
    def denomination(self) -> Decimal | None:
        for record in self.records:
            if record.denomination is not None:
                return record.denomination
        return None

    @property
    def kind(self) -> str:
        kinds = [record.kind for record in self.records]
        return max(set(kinds), key=kinds.count)

    @property
    def title(self) -> str:
        for source in (SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA):
            for record in self.records:
                if record.source == source and record.title_uk:
                    return strip_source_suffix(record.title_uk)
        return next((record.title_ru for record in self.records if record.title_ru), "") or ""

    def record_of(self, source: str) -> SourceRecord | None:
        return next((record for record in self.records if record.source == source), None)

    def to_dict(self) -> dict[str, Any]:
        denomination = self.denomination
        return {
            "title": self.title,
            "year": self.year,
            "denomination": None if denomination is None else str(denomination),
            "kind": self.kind,
            "sources": sorted(self.sources),
            "records": [
                {"source": r.source, "sourceId": r.source_id, "title": r.title_uk, "url": r.url}
                for r in self.records
            ],
        }


def cluster_records(sources: dict[str, list[SourceRecord]]) -> list[Cluster]:
    """Union-find over records: equal keys first, then a fuzzy pass.

    Records of the same source never merge with each other: two rows of one
    site are two products (a coin and its souvenir packaging, say).
    """
    records = [record for name in sources for record in sources[name]]
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    def members(index: int) -> set[str]:
        root = find(index)
        return {records[i].source for i in range(len(records)) if find(i) == root}

    by_key: dict[str, list[int]] = defaultdict(list)
    by_slot: dict[tuple[str, int | None], list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        by_slot[_slot(record.denomination, record.year)].append(index)
        for key in record_keys(record):
            by_key[key].append(index)

    for indexes in by_key.values():
        first = indexes[0]
        for other in indexes[1:]:
            if (
                records[other].source != records[first].source
                and records[other].kind == records[first].kind
                and records[other].source not in members(first)
            ):
                union(first, other)

    for indexes in by_slot.values():
        for position, left in enumerate(indexes):
            for right in indexes[position + 1 :]:
                if records[left].source == records[right].source or find(left) == find(right):
                    continue
                if records[right].source in members(left) or records[left].source in members(right):
                    continue
                if records[left].kind != records[right].kind:
                    continue
                left_titles = [normalize_title(t) for t in source_titles(records[left])]
                right_titles = [normalize_title(t) for t in source_titles(records[right])]
                pairs = [(a, b) for a in left_titles for b in right_titles]
                score = max((float(fuzz.token_sort_ratio(a, b)) for a, b in pairs), default=0.0)
                # The prefix rule of the integration doc applies here too:
                # Wikipedia likes "… в Лондоні" where the NBU stops earlier.
                if score >= CROSS_SOURCE_THRESHOLD or any(
                    titles_equivalent(a, b) for a, b in pairs
                ):
                    union(left, right)

    groups: dict[int, list[SourceRecord]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[find(index)].append(record)
    return [Cluster(group) for group in groups.values()]


# ---------------------------------------------------------------- year table
def build_year_table(
    sources: dict[str, list[SourceRecord]],
    clusters: list[Cluster],
    items: list[CatalogEntry],
) -> list[dict[str, Any]]:
    active = [name for name, records in sources.items() if records]
    years: set[int] = set()
    counts: dict[str, dict[int, int]] = {name: defaultdict(int) for name in sources}
    sets: dict[str, dict[int, int]] = {name: defaultdict(int) for name in sources}
    for name, records in sources.items():
        for record in records:
            if record.year is None:
                continue
            years.add(record.year)
            if record.kind == "coin":
                counts[name][record.year] += 1
            elif record.kind == "set":
                sets[name][record.year] += 1
    ours_total: dict[int, int] = defaultdict(int)
    ours_commemorative: dict[int, int] = defaultdict(int)
    for item in items:
        years.add(item.issue_year)
        ours_total[item.issue_year] += 1
        if item.collection_group in COMMEMORATIVE_GROUPS:
            ours_commemorative[item.issue_year] += 1
    disputed: dict[int, list[str]] = defaultdict(list)
    for cluster in clusters:
        year = cluster.year
        if year is None or cluster.kind != "coin" or len(cluster.sources) >= len(active):
            continue
        if len(disputed[year]) < MAX_DISPUTED_PER_YEAR:
            disputed[year].append(f"{cluster.title} [{', '.join(sorted(cluster.sources))}]")

    rows: list[dict[str, Any]] = []
    for year in sorted(years):
        values = [counts[name][year] for name in active]
        spread = (max(values) - min(values)) if values else 0
        rows.append(
            {
                "year": year,
                **{name: counts[name][year] for name in sources},
                "sets": {name: sets[name][year] for name in sources if sets[name][year]},
                "ours": ours_total[year],
                "oursCommemorative": ours_commemorative[year],
                "spread": spread,
                "flag": "" if spread == 0 else ("~" if spread <= 2 else "!"),
                "disputed": disputed.get(year, []),
            }
        )
    return rows


# -------------------------------------------------------------- series table
def load_series_map(path: Path = SERIES_MAP_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = payload["entries"]
    return entries


def build_series_table(
    ua_coins_series: list[SeriesCount],
    nbu_records: list[SourceRecord],
    ours: list[SeriesEntry],
    series_map: list[dict[str, Any]],
) -> dict[str, Any]:
    nbu_counts: dict[str, int] = defaultdict(int)
    for record in nbu_records:
        if record.series:
            nbu_counts[normalize_title(record.series)] += 1
    ua_by_slug = {series.slug: series for series in ua_coins_series}
    ours_by_name: dict[str, SeriesEntry] = {}
    for series in ours:
        for name in (series.name_original, series.name_ru, series.name_en):
            if name:
                ours_by_name[normalize_title(name)] = series

    rows: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    used_ours: set[int] = set()
    used_nbu: set[str] = set()
    for entry in series_map:
        nbu_name = entry.get("nbu")
        slug = entry.get("ua_coins")
        ua = ua_by_slug.get(slug) if slug else None
        our_series = None
        for alias in entry.get("ours", []):
            our_series = ours_by_name.get(normalize_title(alias))
            if our_series is not None:
                break
        if ua is not None:
            used_slugs.add(ua.slug)
        if our_series is not None:
            used_ours.add(our_series.id)
        nbu_key = normalize_title(nbu_name) if nbu_name else None
        if nbu_key:
            used_nbu.add(nbu_key)
        ua_total = ua.total if ua else None
        nbu_total = nbu_counts.get(nbu_key) if nbu_key else None
        ours_total = our_series.active_item_count if our_series else None
        known = [value for value in (ua_total, nbu_total, ours_total) if value is not None]
        rows.append(
            {
                "series": nbu_name or (ua.name if ua else None),
                "uaCoinsSlug": slug,
                "uaCoinsName": ua.name if ua else None,
                "uaCoins": ua_total,
                "uaCoinsBase": ua.base_metal if ua else None,
                "uaCoinsPrecious": ua.precious_metal if ua else None,
                "nbu": nbu_total,
                "oursSeries": our_series.name_original if our_series else None,
                "ours": ours_total,
                "spread": (max(known) - min(known)) if known else None,
                "note": entry.get("note"),
            }
        )
    unmapped_ua = [
        {"name": s.name, "slug": s.slug, "total": s.total}
        for s in ua_coins_series
        if s.slug not in used_slugs
    ]
    unmapped_nbu = [
        {"name": name, "count": count}
        for name, count in sorted(nbu_counts.items())
        if name not in used_nbu
    ]
    unmapped_ours = [
        {"id": s.id, "name": s.name_original, "count": s.active_item_count}
        for s in ours
        if s.id not in used_ours
    ]
    return {
        "rows": rows,
        "unmappedUaCoins": unmapped_ua,
        "unmappedNbu": unmapped_nbu,
        "unmappedOurs": unmapped_ours,
    }


# ------------------------------------------------------- unmatched, candidates
def unmatched_items(items: list[CatalogEntry], result: MatchResult) -> list[dict[str, Any]]:
    matched = set(result.by_item())
    return [
        {
            "id": item.id,
            "title": item.title_original,
            "titleUk": item.title_uk,
            "year": item.issue_year,
            "denomination": None if item.denomination is None else str(item.denomination),
            "group": item.collection_group,
            "sourceUrl": item.source_url,
        }
        for item in items
        if item.id not in matched
    ]


def candidate_additions(
    clusters: list[Cluster], result: MatchResult, *, minimum_sources: int = 2
) -> list[dict[str, Any]]:
    matched = result.matched_pairs()
    candidates = []
    for cluster in clusters:
        if len(cluster.sources) < minimum_sources or cluster.kind != "coin":
            continue
        if any((record.source, record.source_id) in matched for record in cluster.records):
            continue
        candidates.append(cluster.to_dict())
    candidates.sort(key=lambda c: (c["year"] or 0, c["title"]))
    return candidates


# ------------------------------------------------------------------- prices
def compare_prices(
    items: list[CatalogEntry],
    result: MatchResult,
    ua_coins: list[SourceRecord],
    *,
    sample_size: int = 50,
) -> dict[str, Any]:
    by_id = {record.source_id: record for record in ua_coins}
    items_by_id = {item.id: item for item in items}
    ratios: list[Decimal] = []
    sample: list[dict[str, Any]] = []
    for match in result.matches:
        if match.source != SOURCE_UA_COINS:
            continue
        item = items_by_id.get(match.item_id)
        record = by_id.get(match.source_id)
        if item is None or record is None or record.price is None or not item.last_price:
            continue
        ratio = record.price / item.last_price
        ratios.append(ratio)
        if len(sample) < sample_size:
            sample.append(
                {
                    "itemId": item.id,
                    "title": item.title_original,
                    "ourPrice": str(item.last_price),
                    "ourSource": item.last_price_source,
                    "ourObservedAt": item.last_price_at,
                    "ourSuspect": item.last_price_suspect,
                    "uaCoinsPrice": str(record.price),
                    "uaCoinsDate": record.price_date,
                    "ratio": float(round(ratio, 2)),
                }
            )
    if not ratios:
        return {"compared": 0, "sample": sample}
    ordered = sorted(ratios)
    return {
        "compared": len(ratios),
        "median": float(round(median(ordered), 3)),
        "p10": float(round(ordered[int(len(ordered) * 0.1)], 3)),
        "p90": float(round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))], 3)),
        "min": float(round(ordered[0], 3)),
        "max": float(round(ordered[-1], 3)),
        "offByFactorOf3": sum(1 for r in ratios if r > 3 or r < Decimal("0.3333")),
        "offByFactorOf10": sum(1 for r in ratios if r > 10 or r < Decimal("0.1")),
        "sample": sample,
    }


# ------------------------------------------------------------------- titles
_ABBREVIATION_RE = re.compile(r"\b(ім|м|св|р|рр|ст|вул|о|акад)\.", re.IGNORECASE)


def _difference_kind(titles: dict[str, str]) -> str:
    raw = list(titles.values())
    normalized = [normalize_title(strip_source_suffix(t)) for t in raw]
    if len(set(raw)) == 1:
        return "identical"
    if len(set(normalized)) == 1:
        return "punctuation_or_quotes"
    if any(_ABBREVIATION_RE.search(t) for t in raw):
        return "abbreviation"
    lengths = sorted(normalized, key=len)
    if all(titles_equivalent(lengths[0], other) for other in lengths[1:]):
        return "prefix"
    return "other"


def compare_titles(
    clusters: list[Cluster],
    items: list[CatalogEntry],
    result: MatchResult,
    *,
    examples: int = 20,
) -> dict[str, Any]:
    items_by_id = {item.id: item for item in items}
    ours_by_pair: dict[tuple[str, str], CatalogEntry] = {}
    for match in result.matches:
        item = items_by_id.get(match.item_id)
        if item is not None:
            ours_by_pair[(match.source, match.source_id)] = item
    kinds: dict[str, int] = defaultdict(int)
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        titles = {record.source: record.title_uk for record in cluster.records if record.title_uk}
        if len(titles) < 2:
            continue
        kind = _difference_kind(titles)
        kinds[kind] += 1
        if kind == "identical" or len(samples[kind]) >= examples:
            continue
        ours = next(
            (
                ours_by_pair[(record.source, record.source_id)]
                for record in cluster.records
                if (record.source, record.source_id) in ours_by_pair
            ),
            None,
        )
        samples[kind].append(
            {
                "year": cluster.year,
                "denomination": None if cluster.denomination is None else str(cluster.denomination),
                **titles,
                "ours": ours.title_original if ours else None,
                "oursUk": ours.title_uk if ours else None,
            }
        )
    return {"kinds": dict(kinds), "examples": dict(samples)}


def catalog_overview(snapshot: CatalogSnapshot) -> dict[str, Any]:
    items = snapshot.items
    groups: dict[str, int] = defaultdict(int)
    for item in items:
        groups[item.collection_group] += 1
    return {
        "countryId": snapshot.country_id,
        "items": len(items),
        "active": sum(1 for item in items if not item.is_archived),
        "byGroup": dict(groups),
        "withTitleUk": sum(1 for item in items if item.title_uk),
        "withPhoto": sum(1 for item in items if item.has_photo),
        "withSourceUrlUaCoins": sum(
            1 for item in items if item.source_url and "ua-coins.info" in item.source_url
        ),
        "withSourceUrlUcoin": sum(
            1 for item in items if item.source_url and "ucoin" in item.source_url
        ),
        "withPrice": sum(1 for item in items if item.last_price is not None),
        "withSuspectPrice": sum(1 for item in items if item.last_price_suspect),
        "series": len(snapshot.series),
        "yearRange": [
            min((item.issue_year for item in items), default=None),
            max((item.issue_year for item in items), default=None),
        ],
    }
