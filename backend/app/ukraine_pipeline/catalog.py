"""Our side of the pipeline: the shared Ukrainian catalogue, read and written.

Only shared records take part (created_by IS NULL): the pipeline speaks for the
issuer, and personal items belong to their authors
(docs/04-business-rules.md, rule 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CoinSeries,
    Country,
    Denomination,
    MarketPriceSnapshot,
    PriceSourceLink,
)
from app.reference_data.countries import UKRAINE_CODE
from app.reference_data.denominations import UNITS
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA

# The names price_source_links already uses for these sites. Keeping them means
# the 594 ua-coins links the legacy database holds are updated, not duplicated.
LINK_SOURCES = {
    SOURCE_UA_COINS: "UA-Coins",
    SOURCE_NBU: "NBU",
    SOURCE_WIKIPEDIA: "Wikipedia",
}
COMMEMORATIVE_GROUPS = ("commemorative", "collector")


@dataclass
class OurItem:
    """One shared Ukrainian catalogue record, as the pipeline sees it."""

    id: int
    title_original: str
    title_uk: str | None
    title_en: str | None
    issue_year: int
    denomination: Decimal | None
    denomination_id: int | None
    collection_group: str
    series_id: int | None
    series_name: str | None
    is_archived: bool
    # source -> external id, from price_source_links, the legacy source_key or
    # the URL of the newest shared price snapshot.
    links: dict[str, str] = field(default_factory=dict)

    @property
    def is_commemorative(self) -> bool:
        return self.collection_group in COMMEMORATIVE_GROUPS


async def ukraine_country_id(session: AsyncSession) -> int | None:
    return (
        await session.execute(select(Country.id).where(Country.code == UKRAINE_CODE))
    ).scalar_one_or_none()


def face_value(unit: str | None, value: Decimal | None) -> Decimal | None:
    """The face value the sources print: 5 for "5 гривень", 50 for "50 копійок"."""
    if unit is None or value is None or unit not in UNITS:
        return None
    return (value * UNITS[unit].minor_units) / Decimal(100)


async def load_items(session: AsyncSession, country_id: int) -> list[OurItem]:
    query = (
        select(CatalogItem, CoinSeries.name_original, Denomination.unit, Denomination.value)
        .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
        .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
        .where(CatalogItem.country_id == country_id, CatalogItem.created_by.is_(None))
        .order_by(CatalogItem.issue_year, CatalogItem.id)
    )
    items = [
        OurItem(
            id=item.id,
            title_original=item.title_original,
            title_uk=item.title_uk,
            title_en=item.title_en,
            issue_year=item.issue_year,
            denomination=face_value(unit, value),
            denomination_id=item.denomination_id,
            collection_group=str(item.collection_group),
            series_id=item.series_id,
            series_name=series_name,
            is_archived=item.is_archived,
        )
        for item, series_name, unit, value in (await session.execute(query)).all()
    ]
    await _attach_links(session, items)
    return items


async def _attach_links(session: AsyncSession, items: list[OurItem]) -> None:
    by_id = {item.id: item for item in items}
    if not by_id:
        return
    reverse = {name: source for source, name in LINK_SOURCES.items()}

    links = await session.execute(
        select(PriceSourceLink.catalog_item_id, PriceSourceLink.source, PriceSourceLink.external_id)
    )
    for item_id, source, external_id in links.all():
        item = by_id.get(item_id)
        canonical = reverse.get(source)
        if item is not None and canonical is not None:
            item.links[canonical] = external_id

    # The legacy database also left ua-coins references in the source key and
    # in the URL of the price snapshots; both are worth reading.
    fallback = await session.execute(
        select(CatalogItem.id, CatalogItem.source_key).where(
            CatalogItem.id.in_(by_id), CatalogItem.source_key.is_not(None)
        )
    )
    for item_id, source_key in fallback.all():
        item = by_id[item_id]
        if "ua-coins.info" in (source_key or "") and SOURCE_UA_COINS not in item.links:
            item.links[SOURCE_UA_COINS] = source_key

    snapshots = await session.execute(
        select(MarketPriceSnapshot.catalog_item_id, MarketPriceSnapshot.source_url)
        .where(
            MarketPriceSnapshot.catalog_item_id.in_(by_id),
            MarketPriceSnapshot.created_by.is_(None),
            MarketPriceSnapshot.source_url.is_not(None),
            or_(
                MarketPriceSnapshot.source_url.contains("ua-coins.info"),
                MarketPriceSnapshot.source_url.contains("ua-coins"),
            ),
        )
        .order_by(MarketPriceSnapshot.observed_at.desc())
    )
    for item_id, url in snapshots.all():
        item = by_id[item_id]
        item.links.setdefault(SOURCE_UA_COINS, url or "")
