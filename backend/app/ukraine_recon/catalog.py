"""Our own catalogue: the Ukrainian part of the shared catalogue, read-only.

The reconnaissance runs against the production database on the server, but
the triangulation is easier to iterate on locally. Hence the JSON round trip:
`--catalog-export` writes what was read, `--catalog-from` reads it back
instead of touching a database at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CoinSeries,
    Country,
    Denomination,
    MarketPriceSnapshot,
    MediaFile,
    PriceSourceLink,
)
from app.reference_data.denominations import UNITS, render_label
from app.ukraine_recon.normalize import match_key

UKRAINE_NAMES = ("Україна", "Украина", "Ukraine")
UKRAINE_CODE = "UA"


@dataclass
class CatalogEntry:
    id: int
    title_original: str
    original_lang: str
    title_uk: str | None
    title_en: str | None
    denomination_label: str | None
    denomination: Decimal | None
    issue_year: int
    issue_date: str | None
    collection_group: str
    series_id: int | None
    series_name: str | None
    # The first ua-coins.info reference we hold: the legacy source key, the
    # URL of the latest central price snapshot, or a price source link. The
    # catalogue row itself has no URL column.
    source_url: str | None
    source_key: str | None
    source_links: list[str]
    catalog_km: str | None
    catalog_uc: str | None
    catalog_numista: str | None
    mintage: int | None
    material: str | None
    has_photo: bool
    photo_sources: list[str]
    is_archived: bool
    last_price: Decimal | None
    last_price_source: str | None
    last_price_at: str | None
    last_price_suspect: bool | None

    @property
    def titles(self) -> list[str]:
        """Every title we hold, deduplicated, original first."""
        seen: list[str] = []
        for title in (self.title_original, self.title_uk, self.title_en):
            if title and title not in seen:
                seen.append(title)
        return seen

    def match_keys(self) -> list[str]:
        return [match_key(self.denomination, self.issue_year, title) for title in self.titles]

    def to_dict(self) -> dict[str, Any]:
        payload = self.__dict__.copy()
        payload["denomination"] = None if self.denomination is None else str(self.denomination)
        payload["last_price"] = None if self.last_price is None else str(self.last_price)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CatalogEntry:
        data = dict(payload)
        data["denomination"] = (
            None if data.get("denomination") is None else Decimal(str(data["denomination"]))
        )
        data["last_price"] = (
            None if data.get("last_price") is None else Decimal(str(data["last_price"]))
        )
        data.setdefault("photo_sources", [])
        data.setdefault("source_links", [])
        data.setdefault("original_lang", "uk")
        # An export written before the three-language model still loads: keys
        # the record no longer has are dropped rather than blowing up a run.
        known = {field.name for field in fields(cls)}
        return cls(**{name: value for name, value in data.items() if name in known})


@dataclass
class SeriesEntry:
    id: int
    name_original: str
    name_uk: str | None
    name_en: str | None
    item_count: int
    active_item_count: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SeriesEntry:
        return cls(**payload)


@dataclass
class CatalogSnapshot:
    country_id: int | None
    items: list[CatalogEntry] = field(default_factory=list)
    series: list[SeriesEntry] = field(default_factory=list)
    taken_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "countryId": self.country_id,
            "takenAt": self.taken_at,
            "items": [item.to_dict() for item in self.items],
            "series": [series.to_dict() for series in self.series],
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> CatalogSnapshot:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            country_id=payload.get("countryId"),
            taken_at=payload.get("takenAt"),
            items=[CatalogEntry.from_dict(item) for item in payload["items"]],
            series=[SeriesEntry.from_dict(series) for series in payload["series"]],
        )


def _ukraine_filter() -> Select[tuple[int]]:
    return select(Country.id).where(
        or_(Country.code == UKRAINE_CODE, Country.name_original.in_(UKRAINE_NAMES))
    )


def _denomination_of(entry: Denomination | None) -> Decimal | None:
    """The face value in the currency's main unit — 5 for "5 гривень".

    The sources print the denomination that way, so that is what the match key
    compares.
    """
    if entry is None or entry.unit not in UNITS:
        return None
    return (Decimal(entry.value) * UNITS[entry.unit].minor_units) / Decimal(100)


async def load_catalog(session: AsyncSession) -> CatalogSnapshot:
    """Shared-catalogue Ukrainian items (created_by IS NULL) plus series counts."""
    country_id = (await session.execute(_ukraine_filter())).scalars().first()
    snapshot = CatalogSnapshot(country_id=country_id, taken_at=date.today().isoformat())
    if country_id is None:
        return snapshot

    latest_at = (
        select(
            MarketPriceSnapshot.catalog_item_id.label("item_id"),
            func.max(MarketPriceSnapshot.observed_at).label("observed_at"),
        )
        .where(MarketPriceSnapshot.created_by.is_(None))
        .group_by(MarketPriceSnapshot.catalog_item_id)
        .subquery()
    )
    latest = (
        select(
            MarketPriceSnapshot.catalog_item_id,
            MarketPriceSnapshot.price,
            MarketPriceSnapshot.source,
            MarketPriceSnapshot.observed_at,
            MarketPriceSnapshot.is_suspect,
            MarketPriceSnapshot.source_url,
        )
        .join(
            latest_at,
            and_(
                MarketPriceSnapshot.catalog_item_id == latest_at.c.item_id,
                MarketPriceSnapshot.observed_at == latest_at.c.observed_at,
            ),
        )
        .where(MarketPriceSnapshot.created_by.is_(None))
    )
    prices: dict[int, tuple[Decimal, str, str, bool, str | None]] = {}
    for item_id, price, source, observed_at, suspect, url in (await session.execute(latest)).all():
        prices.setdefault(item_id, (price, source, observed_at.isoformat(), bool(suspect), url))

    links: dict[int, list[str]] = {}
    link_rows = select(
        PriceSourceLink.catalog_item_id, PriceSourceLink.source, PriceSourceLink.external_id
    ).order_by(PriceSourceLink.id)
    for item_id, source, external_id in (await session.execute(link_rows)).all():
        links.setdefault(item_id, []).append(f"{source}:{external_id}")

    photos = (
        select(MediaFile.catalog_item_id, MediaFile.source)
        .where(MediaFile.catalog_item_id.is_not(None), MediaFile.owner_id.is_(None))
        .distinct()
    )
    photo_sources: dict[int, list[str]] = {}
    for item_id, source in (await session.execute(photos)).all():
        photo_sources.setdefault(item_id, []).append(str(source))

    query = (
        select(CatalogItem, CoinSeries, Denomination)
        .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
        .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
        .where(CatalogItem.country_id == country_id, CatalogItem.created_by.is_(None))
        .order_by(CatalogItem.issue_year, CatalogItem.id)
    )
    for item, series, denomination in (await session.execute(query)).all():
        price = prices.get(item.id)
        label = (
            None
            if denomination is None
            else render_label(denomination.value, denomination.unit, "uk")
        )
        item_links = links.get(item.id, [])
        references = [item.source_key, price[4] if price else None, *item_links]
        source_url = next((ref for ref in references if ref and "ua-coins.info" in ref), None)
        snapshot.items.append(
            CatalogEntry(
                id=item.id,
                title_original=item.title_original,
                original_lang=item.original_lang,
                title_uk=item.title_uk,
                title_en=item.title_en,
                denomination_label=label,
                denomination=_denomination_of(denomination),
                issue_year=item.issue_year,
                issue_date=item.issue_date.isoformat() if item.issue_date else None,
                collection_group=str(item.collection_group),
                series_id=item.series_id,
                series_name=series.name_original if series is not None else None,
                source_url=source_url,
                source_key=item.source_key,
                source_links=item_links,
                catalog_km=item.catalog_km,
                catalog_uc=item.catalog_uc,
                catalog_numista=item.catalog_numista,
                mintage=item.mintage_announced,
                material=item.material,
                has_photo=item.id in photo_sources,
                photo_sources=sorted(photo_sources.get(item.id, [])),
                is_archived=item.is_archived,
                last_price=price[0] if price else None,
                last_price_source=price[1] if price else None,
                last_price_at=price[2] if price else None,
                last_price_suspect=price[3] if price else None,
            )
        )

    counts = (
        select(
            CoinSeries,
            func.count(CatalogItem.id),
            func.count(CatalogItem.id).filter(CatalogItem.is_archived.is_(False)),
        )
        .outerjoin(
            CatalogItem,
            and_(CatalogItem.series_id == CoinSeries.id, CatalogItem.created_by.is_(None)),
        )
        .where(CoinSeries.country_id == country_id)
        .group_by(CoinSeries.id)
        .order_by(CoinSeries.name_original)
    )
    for series, total, active in (await session.execute(counts)).all():
        snapshot.series.append(
            SeriesEntry(
                id=series.id,
                name_original=series.name_original,
                name_uk=series.name_uk,
                name_en=series.name_en,
                item_count=int(total),
                active_item_count=int(active),
            )
        )
    return snapshot


def has_shared_items(snapshot: CatalogSnapshot) -> bool:
    return bool(snapshot.items)


__all__ = [
    "CatalogEntry",
    "CatalogSnapshot",
    "SeriesEntry",
    "exists",
    "has_shared_items",
    "load_catalog",
]
