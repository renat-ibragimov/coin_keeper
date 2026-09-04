"""gaps — the coins the sources have and we do not.

After the bridge every cluster either belongs to one of our records or belongs
to nothing. The second kind, when the National Bank has a card for it, becomes
a new shared catalogue record: the issuer says the coin exists, so it does.

Only coins are created. A mint set is a product, not a coin, and circulation
issues are not in the numismatic catalogue at all — both are counted in the
report and skipped.

Idempotent by source_key ("nbu:<card id>"), which the schema already keeps
unique among shared records: a second run inserts nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Denomination, Material
from app.models.enums import CollectionGroup, MetalKind, TranslationSource
from app.reference_data.denominations import DenominationParseError, parse_label
from app.reference_data.materials import parse_material
from app.ukraine_pipeline.series import ensure_series, series_by_name
from app.ukraine_pipeline.sources import Sources, cluster_key, coin_clusters, nbu_title
from app.ukraine_recon.models import SOURCE_NBU
from app.ukraine_recon.normalize import parse_date
from app.ukraine_recon.triangulate import Cluster

SOURCE_KEY_PREFIX = "nbu:"
PRECIOUS_CODES = ("silver", "gold", "platinum")


@dataclass
class GapsOutcome:
    created: list[dict[str, Any]] = field(default_factory=list)
    skipped_no_nbu: int = 0
    skipped_not_coin: int = 0
    skipped_existing: int = 0
    problems: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "created": len(self.created),
            "skippedWithoutNbuCard": self.skipped_no_nbu,
            "skippedNotACoin": self.skipped_not_coin,
            "skippedAlreadyPresent": self.skipped_existing,
            "problems": len(self.problems),
        }


def source_key_for(cluster: Cluster) -> str | None:
    record = cluster.record_of(SOURCE_NBU)
    return None if record is None else f"{SOURCE_KEY_PREFIX}{record.source_id}"


def metal_kind_of(composition: str | None) -> MetalKind:
    if composition is None:
        return MetalKind.UNKNOWN
    return MetalKind.PRECIOUS if composition.startswith(PRECIOUS_CODES) else MetalKind.BASE


async def _denomination_id(
    session: AsyncSession,
    *,
    country_id: int,
    label: str | None,
    cache: dict[str, int],
) -> int | None:
    """The denomination row for an NBU "Номінал", created when missing."""
    if not label:
        return None
    if label in cache:
        return cache[label]
    try:
        parsed = parse_label(label, country_code="UA")
    except DenominationParseError:
        return None
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
    cache[label] = existing
    return existing


async def create_missing(
    session: AsyncSession,
    *,
    country_id: int,
    sources: Sources,
    linked_keys: set[str],
    dry_run: bool,
    limit: int | None = None,
) -> GapsOutcome:
    outcome = GapsOutcome()
    materials = {
        code: material_id
        for material_id, code in (await session.execute(select(Material.id, Material.code))).all()
    }
    series_cache = await series_by_name(session, country_id)
    denomination_cache: dict[str, int] = {}
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
        key = f"{SOURCE_KEY_PREFIX}{record.source_id}"
        if key in existing_keys:
            outcome.skipped_existing += 1
            continue

        title_uk = nbu_title(record)
        if not title_uk or record.year is None:
            outcome.problems.append(f"{key}: no title or no year")
            continue
        english = sources.nbu_english.get(record.source_id)
        composition = parse_material(record.metal)
        series = None
        if record.series:
            english_series = english.series if english is not None else None
            series = (
                None
                if dry_run
                else await ensure_series(
                    session,
                    country_id=country_id,
                    name_uk=record.series,
                    name_en=english_series,
                    cache=series_cache,
                )
            )

        outcome.created.append(
            {
                "sourceKey": key,
                "title": title_uk,
                "titleEn": english.title if english is not None else None,
                "year": record.year,
                "denomination": record.denomination_label,
                "series": record.series,
            }
        )
        if not dry_run:
            session.add(
                _build_item(
                    country_id=country_id,
                    key=key,
                    title_uk=title_uk,
                    title_en=english.title if english is not None else None,
                    record_year=record.year,
                    issue_date=parse_date(record.issue_date),
                    mintage=record.mintage,
                    mintage_actual=record.mintage_actual,
                    series_id=series.id if series is not None else None,
                    denomination_id=await _denomination_id(
                        session,
                        country_id=country_id,
                        label=record.denomination_label,
                        cache=denomination_cache,
                    ),
                    composition_id=materials.get(composition.composition or ""),
                    metal_kind=metal_kind_of(composition.composition),
                    material=None if composition.composition else record.metal,
                    weight=composition.weight_grams or _decimal(record.extra.get("massGrams")),
                    diameter=composition.diameter_mm or _decimal(record.extra.get("diameterMm")),
                    edge=record.extra.get("edge"),
                )
            )
        existing_keys.add(key)
        if limit is not None and len(outcome.created) >= limit:
            break

    if not dry_run:
        await session.flush()
    return outcome


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", ".").strip()
    try:
        return Decimal(text)
    except (ArithmeticError, ValueError):
        return None


def _build_item(
    *,
    country_id: int,
    key: str,
    title_uk: str,
    title_en: str | None,
    record_year: int,
    issue_date: date | None,
    mintage: int | None,
    mintage_actual: int | None,
    series_id: int | None,
    denomination_id: int | None,
    composition_id: int | None,
    metal_kind: MetalKind,
    material: str | None,
    weight: Decimal | None,
    diameter: Decimal | None,
    edge: str | None,
) -> CatalogItem:
    return CatalogItem(
        country_id=country_id,
        series_id=series_id,
        denomination_id=denomination_id,
        collection_group=CollectionGroup.COMMEMORATIVE,
        title_original=title_uk,
        original_lang="uk",
        title_uk=title_uk,
        title_uk_source=TranslationSource.OFFICIAL,
        title_en=title_en,
        title_en_source=TranslationSource.OFFICIAL if title_en else None,
        issue_year=record_year,
        issue_date=issue_date,
        mintage_announced=mintage,
        mintage_actual=mintage_actual,
        composition_id=composition_id,
        material=material,
        metal_kind=metal_kind,
        weight_grams=weight,
        diameter_mm=diameter,
        edge=edge,
        source_key=key,
        created_by=None,
    )
