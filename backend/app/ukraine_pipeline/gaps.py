"""gaps — the coins the sources have and we do not.

After the bridge every cluster either belongs to one of our records or belongs
to nothing. The second kind, when the National Bank has a card for it, becomes
a new shared catalogue record: the issuer says the coin exists, so it does.

Only coins are created. A mint set is a product, not a coin, and a roll of
circulation commemoratives is a product too — the coin inside it is read off
the card for the sake of matching (app/ukraine_pipeline/sources.py), but its
card states no metal and no series, so nothing is created from one. Both are
counted in the report and skipped.

A record is created with everything the cluster knows, not with a name and a
year: the face value as a denominations row, the series, the composition, the
metal kind, the mass, the diameter and the edge. `read_cluster` is the one
place that turns a cluster into our columns, and the repair step
(app/ukraine_pipeline/repair.py) uses it to fill in records an earlier run
left half empty.

Nothing is created on top of a record we already have. A cluster whose year
and face value match one of our own unlinked records is a duplicate waiting to
happen — the bridge simply failed to score the two together — so instead of a
second row it produces a review line marked `would_duplicate`, and a person
says whether it is the same coin.

Idempotent by source_key ("nbu:<card id>"), which the schema already keeps
unique among shared records: a second run inserts nothing.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Denomination, Material
from app.models.enums import CollectionGroup, MetalKind, TranslationSource
from app.reference_data.denominations import (
    UNITS,
    DenominationParseError,
    ParsedDenomination,
    parse_label,
)
from app.reference_data.materials import parse_material
from app.ukraine_pipeline import bridge
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.lexicon import Lexicon, load_lexicon
from app.ukraine_pipeline.series import ensure_series, series_by_name
from app.ukraine_pipeline.sources import (
    NbuEnglish,
    Sources,
    cluster_key,
    coin_clusters,
    nbu_metal,
    nbu_title,
)
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA, SourceRecord
from app.ukraine_recon.normalize import normalize_title, parse_date
from app.ukraine_recon.triangulate import Cluster

SOURCE_KEY_PREFIX = "nbu:"
# The order of trust when two sources state the same field differently.
TRUST_ORDER = (SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA)
# The unit the sources print a face value in when they print only a number.
DEFAULT_UNITS = {"UAH": "hryvnia", "UAK": "karbovanets"}
DUPLICATE_NOTE = "would_duplicate"
MAX_DUPLICATE_CANDIDATES = 5
DUPLICATES_CSV_COLUMNS = (*bridge.CSV_COLUMNS, "note")


@dataclass
class GapsOutcome:
    created: list[dict[str, Any]] = field(default_factory=list)
    # Clusters not created because one of our own records is already sitting
    # in that year and face value, unlinked. One row per pair, for review.
    would_duplicate: list[dict[str, Any]] = field(default_factory=list)
    skipped_no_nbu: int = 0
    skipped_not_coin: int = 0
    skipped_existing: int = 0
    skipped_roll: int = 0
    problems: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "created": len(self.created),
            "wouldDuplicate": len(self.would_duplicate),
            "skippedWithoutNbuCard": self.skipped_no_nbu,
            "skippedNotACoin": self.skipped_not_coin,
            "skippedAlreadyPresent": self.skipped_existing,
            "skippedRollOnly": self.skipped_roll,
            "problems": len(self.problems),
        }


# ------------------------------------------------------------ reading a coin
@dataclass(frozen=True, slots=True)
class CoinFields:
    """Everything a cluster says about one coin, in our own columns."""

    source_key: str
    title_uk: str
    title_en: str | None
    year: int
    issue_date: date | None
    mintage: int | None
    mintage_actual: int | None
    denomination: ParsedDenomination | None
    series_uk: str | None
    series_en: str | None
    composition_code: str | None
    metal_kind: MetalKind
    material: str | None
    weight_grams: Decimal | None
    diameter_mm: Decimal | None
    edge: str | None


def _in_trust_order(cluster: Cluster) -> list[SourceRecord]:
    ordered = [cluster.record_of(source) for source in TRUST_ORDER]
    return [record for record in ordered if record is not None]


def denomination_of(cluster: Cluster) -> ParsedDenomination | None:
    """The face value the cluster states, as value + unit + currency.

    Every source writes it differently — the National Bank "1 грн", Wikipedia
    "5 грн." from its column header, ua-coins a bare number — so the first
    label that parses wins, and a cluster with no readable label at all falls
    back to the number plus the currency. The sources print a face value in
    the main unit, which is what makes that fallback safe.
    """
    for record in _in_trust_order(cluster):
        if not record.denomination_label:
            continue
        try:
            return parse_label(record.denomination_label, country_code="UA")
        except DenominationParseError:
            continue
    value = cluster.denomination
    if value is None:
        return None
    currency = next((record.currency for record in _in_trust_order(cluster)), "UAH")
    unit = DEFAULT_UNITS.get(currency)
    if unit is None:
        return None
    return ParsedDenomination(value=value, unit=unit, currency_code=UNITS[unit].currency_code)


def read_cluster(cluster: Cluster, english: dict[str, NbuEnglish]) -> CoinFields | None:
    """One cluster as our columns, or None when the issuer has no card for it."""
    record = cluster.record_of(SOURCE_NBU)
    if record is None:
        return None
    title_uk = nbu_title(record)
    year = record.year if record.year is not None else cluster.year
    if not title_uk or year is None:
        return None
    card = english.get(record.source_id)
    composition_code, metal_kind = nbu_metal(record.metal)
    parsed_material = parse_material(record.metal)
    return CoinFields(
        source_key=f"{SOURCE_KEY_PREFIX}{record.source_id}",
        title_uk=title_uk,
        title_en=card.title if card is not None and card.title else None,
        year=year,
        issue_date=parse_date(record.issue_date),
        mintage=record.mintage,
        mintage_actual=record.mintage_actual,
        denomination=denomination_of(cluster),
        series_uk=record.series,
        series_en=card.series if card is not None else None,
        composition_code=composition_code,
        # The material text is kept only when nothing recognised it, the way
        # the legacy migration keeps what it could not parse.
        material=None if composition_code else record.metal,
        metal_kind=metal_kind,
        weight_grams=parsed_material.weight_grams or _decimal(record.extra.get("massGrams")),
        diameter_mm=parsed_material.diameter_mm or _decimal(record.extra.get("diameterMm")),
        edge=_edge(record.extra.get("edge")),
    )


def is_roll_derived(cluster: Cluster) -> bool:
    """The coin was read off a roll card: real for matching, not for creating."""
    record = cluster.record_of(SOURCE_NBU)
    return record is not None and bool(record.extra.get("fromRoll"))


def _edge(value: Any) -> str | None:
    """ "<не вказується>" is the NBU's way of writing that it does not say."""
    text = (str(value) if value is not None else "").strip()
    return None if not text or text.startswith("<") else text


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", ".").strip()
    try:
        return Decimal(text)
    except (ArithmeticError, ValueError):
        return None


# ------------------------------------------------------------- our own rows
def _slot(year: int | None, denomination: Decimal | None) -> tuple[int | None, str]:
    return year, "?" if denomination is None else format(denomination.normalize(), "f")


def unlinked_by_slot(
    items: Iterable[OurItem], linked_ids: set[int]
) -> dict[tuple[int | None, str], list[OurItem]]:
    """Our active, unlinked records keyed by year and face value."""
    index: dict[tuple[int | None, str], list[OurItem]] = {}
    for item in items:
        if item.is_archived or item.id in linked_ids:
            continue
        index.setdefault(_slot(item.issue_year, item.denomination), []).append(item)
    return index


def duplicates_of(
    fields: CoinFields,
    index: dict[tuple[int | None, str], list[OurItem]],
    lexicon: Lexicon,
) -> list[tuple[OurItem, float]]:
    """Our unlinked records this cluster would duplicate, likeliest first.

    Same year and same face value is the whole test, plus the series when both
    sides name one: that is exactly the shape the duplicates took — our
    "Пектораль" against the National Bank's card for the same coin, four times
    over. A record whose face value we never recorded counts too; it is the
    likeliest duplicate of all. The score only orders the rows a person reads;
    nothing here decides anything by it.
    """
    value = None if fields.denomination is None else fields.denomination.value
    candidates = list(index.get(_slot(fields.year, value), []))
    if value is not None:
        candidates.extend(index.get(_slot(fields.year, None), []))
    series = normalize_title(fields.series_uk) if fields.series_uk else None
    found: list[tuple[OurItem, float]] = []
    for item in candidates:
        ours = normalize_title(item.series_name) if item.series_name else None
        if series and ours and series != ours:
            continue
        found.append((item, lexicon.score(item.title_original, fields.title_uk)))
    found.sort(key=lambda pair: -pair[1])
    return found[:MAX_DUPLICATE_CANDIDATES]


# ------------------------------------------------------------------ creating
async def ensure_denomination(
    session: AsyncSession,
    *,
    country_id: int,
    parsed: ParsedDenomination | None,
    cache: dict[tuple[str, str, Decimal], int],
) -> int | None:
    """The denominations row for a face value, created when missing."""
    if parsed is None:
        return None
    key = (parsed.currency_code, parsed.unit, parsed.value)
    if key in cache:
        return cache[key]
    existing = (
        await session.execute(
            select(Denomination.id).where(
                Denomination.country_id == country_id,
                Denomination.currency_code == parsed.currency_code,
                Denomination.unit == parsed.unit,
                Denomination.value == parsed.value,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        row = Denomination(
            country_id=country_id,
            currency_code=parsed.currency_code,
            value=parsed.value,
            unit=parsed.unit,
            sort_order=parsed.minor_units,
        )
        session.add(row)
        await session.flush()
        existing = row.id
    cache[key] = existing
    return existing


async def create_missing(
    session: AsyncSession,
    *,
    country_id: int,
    sources: Sources,
    linked_keys: set[str],
    dry_run: bool,
    lexicon: Lexicon | None = None,
    items: Sequence[OurItem] = (),
    linked_ids: set[int] | None = None,
    limit: int | None = None,
) -> GapsOutcome:
    outcome = GapsOutcome()
    lexicon = lexicon or load_lexicon()
    materials = {
        code: material_id
        for material_id, code in (await session.execute(select(Material.id, Material.code))).all()
    }
    series_cache = await series_by_name(session, country_id)
    denomination_cache: dict[tuple[str, str, Decimal], int] = {}
    existing_keys = set(
        (
            await session.execute(
                select(CatalogItem.source_key).where(
                    CatalogItem.created_by.is_(None),
                    CatalogItem.source_key.like(f"{SOURCE_KEY_PREFIX}%"),
                )
            )
        )
        .scalars()
        .all()
    )
    ours = unlinked_by_slot(items, linked_ids or set())

    coins = {id(cluster) for cluster in coin_clusters(sources)}
    for cluster in sources.clusters:
        if cluster_key(cluster) in linked_keys:
            continue
        if id(cluster) not in coins:
            outcome.skipped_not_coin += 1
            continue
        record = cluster.record_of(SOURCE_NBU)
        if record is None:
            # Without a card there is no official name, series or photo, and
            # inventing those is exactly what this stage exists to avoid.
            outcome.skipped_no_nbu += 1
            continue
        if is_roll_derived(cluster):
            # The card is for the roll: it names the coin, which is enough to
            # match it, and states neither its metal nor its series, which is
            # not enough to create it.
            outcome.skipped_roll += 1
            continue
        key = f"{SOURCE_KEY_PREFIX}{record.source_id}"
        if key in existing_keys:
            outcome.skipped_existing += 1
            continue

        fields = read_cluster(cluster, sources.nbu_english)
        if fields is None:
            outcome.problems.append(f"{key}: no title or no year")
            continue

        twins = duplicates_of(fields, ours, lexicon)
        if twins:
            outcome.would_duplicate.extend(
                _duplicate_row(item, score, cluster, fields) for item, score in twins
            )
            continue

        series = None
        if fields.series_uk and not dry_run:
            series = await ensure_series(
                session,
                country_id=country_id,
                name_uk=fields.series_uk,
                name_en=fields.series_en,
                cache=series_cache,
            )
        outcome.created.append(
            {
                "sourceKey": key,
                "title": fields.title_uk,
                "titleEn": fields.title_en,
                "year": fields.year,
                "denomination": record.denomination_label,
                "series": fields.series_uk,
                "metalKind": str(fields.metal_kind),
            }
        )
        if not dry_run:
            session.add(
                _build_item(
                    country_id=country_id,
                    fields=fields,
                    series_id=series.id if series is not None else None,
                    denomination_id=await ensure_denomination(
                        session,
                        country_id=country_id,
                        parsed=fields.denomination,
                        cache=denomination_cache,
                    ),
                    composition_id=materials.get(fields.composition_code or ""),
                )
            )
        existing_keys.add(key)
        if limit is not None and len(outcome.created) >= limit:
            break

    if not dry_run:
        await session.flush()
    return outcome


def _duplicate_row(
    item: OurItem, score: float, cluster: Cluster, fields: CoinFields
) -> dict[str, Any]:
    return {
        "decision": "",
        "itemId": item.id,
        "ourTitle": item.title_original,
        "ourYear": item.issue_year,
        "ourDenomination": item.denomination or "",
        "clusterKey": cluster_key(cluster),
        "clusterTitle": fields.title_uk,
        "clusterYear": fields.year,
        "clusterDenomination": (
            "" if fields.denomination is None else str(fields.denomination.value)
        ),
        "score": round(score, 1),
        "sources": " ".join(sorted(cluster.sources)),
        "claimedBy": "",
        "note": DUPLICATE_NOTE,
    }


def write_duplicates_csv(path: Path, outcome: GapsOutcome) -> int:
    """The would-be duplicates, in the format --apply-review already reads.

    A person writes "yes" against the pair that is one coin; the bridge then
    links our record to that cluster, and the next run of this step finds the
    cluster taken and creates nothing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DUPLICATES_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(outcome.would_duplicate)
    return len(outcome.would_duplicate)


def _build_item(
    *,
    country_id: int,
    fields: CoinFields,
    series_id: int | None,
    denomination_id: int | None,
    composition_id: int | None,
) -> CatalogItem:
    return CatalogItem(
        country_id=country_id,
        series_id=series_id,
        denomination_id=denomination_id,
        collection_group=CollectionGroup.COMMEMORATIVE,
        title_original=fields.title_uk,
        original_lang="uk",
        title_uk=fields.title_uk,
        title_uk_source=TranslationSource.OFFICIAL,
        title_en=fields.title_en,
        title_en_source=TranslationSource.OFFICIAL if fields.title_en else None,
        issue_year=fields.year,
        issue_date=fields.issue_date,
        mintage_announced=fields.mintage,
        mintage_actual=fields.mintage_actual,
        composition_id=composition_id,
        material=fields.material,
        metal_kind=fields.metal_kind,
        weight_grams=fields.weight_grams,
        diameter_mm=fields.diameter_mm,
        edge=fields.edge,
        source_key=fields.source_key,
        created_by=None,
    )
