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
# The prefixes catalog_items.source_key carries. A record the gaps step made
# holds "nbu:1307" and nothing else — no price_source_links row — so a source
# key is a reference exactly like a link is, and the bridge has to read it as
# one or the two records for that coin go to review against each other.
SOURCE_KEY_PREFIXES = {
    "nbu:": SOURCE_NBU,
    "ua-coins:": SOURCE_UA_COINS,
    "ua_coins:": SOURCE_UA_COINS,
    "wikipedia:": SOURCE_WIKIPEDIA,
    "wiki:": SOURCE_WIKIPEDIA,
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
    source_key: str | None = None
    # The unit the face value is in ("kopiika", "hryvnia", ...). Needed
    # alongside `denomination` wherever a face value alone is ambiguous — 1
    # kopiika and 1 hryvnia are both "1" (app/ukraine_pipeline/circ_bridge.py).
    # Defaulted, not loaded, on a record load_items never populates it for —
    # a test built by hand rather than by the query below.
    denomination_unit: str | None = None
    # source -> external id, from price_source_links, the legacy source_key or
    # the URL of the newest shared price snapshot.
    links: dict[str, str] = field(default_factory=dict)

    @property
    def is_commemorative(self) -> bool:
        return self.collection_group in COMMEMORATIVE_GROUPS


def source_key_reference(source_key: str | None) -> tuple[str, str] | None:
    """(source, external id) out of a source key, or None when it names none.

    Both forms count: the prefixed keys the pipeline writes ("nbu:1307") and
    the bare ua-coins.info URL the legacy importer left behind.
    """
    key = (source_key or "").strip()
    if not key:
        return None
    for prefix, source in SOURCE_KEY_PREFIXES.items():
        if key.startswith(prefix):
            external_id = key[len(prefix) :].strip()
            return (source, external_id) if external_id else None
    return (SOURCE_UA_COINS, key) if "ua-coins.info" in key else None


async def ukraine_country_id(session: AsyncSession) -> int | None:
    return (
        await session.execute(select(Country.id).where(Country.code == UKRAINE_CODE))
    ).scalar_one_or_none()


def face_value(unit: str | None, value: Decimal | None) -> Decimal | None:
    """The face value the sources print: 5 for "5 гривень", 50 for "50 копійок".

    Just `value`, gated on the unit being one this code knows — every
    consumer compares this against a raw parsed face value (a Wikipedia or
    NBU cell's own number, never converted to a common subunit), so scaling
    it here would only make hryvnia records match by accident (its
    denominations.UNITS minor_units happens to be 100) and kopiika ones not.
    """
    if unit is None or value is None or unit not in UNITS:
        return None
    return value


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
            source_key=item.source_key,
            denomination_unit=unit,
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

    # The source key is a reference too: the legacy database left ua-coins URLs
    # in it, and the gaps step writes "nbu:<card id>" there.
    for item in items:
        reference = source_key_reference(item.source_key)
        if reference is not None:
            source, external_id = reference
            item.links.setdefault(source, external_id)

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
