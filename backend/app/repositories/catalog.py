"""Catalog data access.

Every query in this repository carries the visibility filter
(created_by IS NULL OR created_by = :user_id) and, unless the archive is
explicitly requested, the verbatim `NOT is_archived` predicate that the partial
indexes expect. Routes never assemble these conditions themselves
(docs/07-auth.md, docs/02-data-model.md).

Listings additionally carry `storefront_visible()` (docs/04-business-rules.md,
§13): a record from a deactivated country drops out of listings and
aggregates unless it is personal or already owned. The single-item card and
its price/instance sub-resources are exempt on purpose — see that function's
docstring.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ColumnElement,
    UnaryExpression,
    and_,
    case,
    exists,
    false,
    func,
    not_,
    or_,
    select,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE, LOCALE_UK
from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Country,
    Denomination,
    EdgeType,
    ExchangeRate,
    Expense,
    MarketPriceSnapshot,
    Material,
    PriceSourceLink,
    QualityType,
)
from app.models.enums import CollectionGroup
from app.repositories.localization import localized


@dataclass
class CatalogFilters:
    q: str | None = None
    country_ids: list[int] | None = None
    series_ids: list[int] | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    denomination_ids: list[int] | None = None
    groups: list[CollectionGroup] | None = None
    material_ids: list[int] | None = None
    owned: bool | None = None
    scope: str = "all"  # all | shared | own
    archived: bool = False
    sort: str = "title"
    order: str = "asc"


@dataclass
class CatalogRow:
    item: CatalogItem
    country: str
    series_name: str | None
    denomination: Denomination | None
    composition: Material | None
    quantity_owned: int
    purchase_total_uah: Decimal
    market_price_uah: Decimal | None
    price_source: str | None
    price_observed_at: datetime | None
    source_url: str | None
    # Card-only: the listing never selects these (docs/08-ui-map.md).
    edge_type: EdgeType | None = None
    quality_type: QualityType | None = None


@dataclass
class CatalogPage:
    rows: list[CatalogRow] = field(default_factory=list)
    total: int = 0


def _display_title(locale: str) -> ColumnElement[str]:
    """title_{locale} → title_original; the original is NOT NULL."""
    return localized(
        locale,
        uk=CatalogItem.title_uk,
        en=CatalogItem.title_en,
        original=CatalogItem.title_original,
    )


def _search_vector() -> ColumnElement[Any]:
    """Must match the GIN index expression verbatim or the index is not used."""
    joined = (
        func.coalesce(CatalogItem.title_original, "")
        + " "
        + func.coalesce(CatalogItem.title_uk, "")
        + " "
        + func.coalesce(CatalogItem.title_en, "")
    )
    return func.to_tsvector("simple", joined)


def storefront_visible(user_id: int, *, require_confirmed: bool = True) -> ColumnElement[bool]:
    """Storefront visibility for a shared catalog record (docs/04-business-rules.md, §13, §13a).

    A record shows when its country is active, when it is the user's own
    personal item, or when the user already holds at least one instance of
    it — an owner keeps finding their coins from a deactivated country.
    Independent of `_visible()` (read permission) and of the archive flag;
    never applied to the single-item card or price/instance sub-resources,
    which stay reachable by id.

    `require_confirmed` (default on) adds the harder gate from §13a on top,
    with no exception for a personal item or an owned instance: an
    unconfirmed country never shows as *the catalogue*, however much of it a
    user has collected. This is what makes `GET /catalog` Ukraine-only today.
    Callers about the user's own collection rather than the catalogue browse
    experience — the dashboard, the series screens — pass `False`: a
    personal collection shows everything its owner actually has, regardless
    of which countries the catalogue project has gotten around to confirming
    (owner's call, 2026-09-12).

    Self-contained EXISTS checks so the caller need not join Country: reused
    verbatim by the series and dashboard repositories. Each subquery pins its
    correlation to CatalogItem alone — the dashboard's breakdown queries join
    Country and CollectionItem directly, and without this SQLAlchemy
    auto-correlates those same tables out of these subqueries entirely.
    """
    visible = or_(
        exists(
            select(Country.id)
            .where(Country.id == CatalogItem.country_id, Country.is_active)
            .correlate(CatalogItem)
        ),
        CatalogItem.created_by == user_id,
        exists(
            select(CollectionItem.id)
            .where(
                CollectionItem.catalog_item_id == CatalogItem.id,
                CollectionItem.owner_id == user_id,
            )
            .correlate(CatalogItem)
        ),
    )
    if not require_confirmed:
        return visible
    return and_(
        exists(
            select(Country.id)
            .where(Country.id == CatalogItem.country_id, Country.catalog_confirmed)
            .correlate(CatalogItem)
        ),
        visible,
    )


def snapshot_visible_to(user_id: int) -> ColumnElement[bool]:
    """Price snapshot visibility (docs/04-business-rules.md, rule 7)."""
    return or_(
        MarketPriceSnapshot.created_by.is_(None),
        MarketPriceSnapshot.created_by == user_id,
    )


def latest_price_uah_for(item_id_col: Any, user_id: int) -> Any:
    """Correlated scalar subquery: the latest visible non-suspect snapshot of
    the given catalog item column, converted to UAH by the newest rate.

    Shared by the series summary and the dashboard, which aggregate it over
    collection items and over missing catalog items.
    """
    latest_rate = (
        select(ExchangeRate.rate_uah)
        .where(ExchangeRate.currency_code == MarketPriceSnapshot.currency_code)
        .order_by(ExchangeRate.effective_date.desc())
        .limit(1)
        .scalar_subquery()
    )
    price_uah = case(
        (MarketPriceSnapshot.currency_code == "UAH", MarketPriceSnapshot.price),
        else_=MarketPriceSnapshot.price * func.coalesce(latest_rate, 0),
    )
    return (
        select(price_uah)
        .where(
            MarketPriceSnapshot.catalog_item_id == item_id_col,
            not_(MarketPriceSnapshot.is_suspect),
            snapshot_visible_to(user_id),
        )
        .order_by(MarketPriceSnapshot.observed_at.desc(), MarketPriceSnapshot.id.desc())
        .limit(1)
        .scalar_subquery()
    )


def has_visible_price(item_id_col: Any, user_id: int) -> ColumnElement[bool]:
    """Whether any usable (non-suspect, visible) snapshot exists at all."""
    return exists(
        select(MarketPriceSnapshot.id).where(
            MarketPriceSnapshot.catalog_item_id == item_id_col,
            not_(MarketPriceSnapshot.is_suspect),
            snapshot_visible_to(user_id),
        )
    )


_SEARCH_WORD = re.compile(r"\w+", re.UNICODE)


def _title_prefix_condition(term: str) -> ColumnElement[bool]:
    """Every word in `term` matched as a *prefix* against the title tsvector,
    so "Одес" already finds "Одеса" — a search box shouldn't demand the whole
    word (owner's call 2026-09-07, many Ukrainian commemoratives name a city).

    Words come from a plain regex, not `to_tsquery(term)` directly: that
    function raises on tsquery operator syntax, so a stray "&" or "(" typed
    into the search box would 500 instead of just matching nothing.
    """
    words = _SEARCH_WORD.findall(term)
    if not words:
        return false()
    prefix_query = " & ".join(f"{word}:*" for word in words)
    return _search_vector().op("@@")(func.to_tsquery("simple", prefix_query))


def catalog_search_condition(q: str) -> ColumnElement[bool]:
    """Full text over titles, plus catalog numbers, country and year.

    Requires Country joined into the query. Shared with the collection listing,
    which searches by the same catalog fields. The country is searched in all
    three of its names, so "Ukraine" finds Ukrainian coins under either locale.
    """
    term = q.strip()
    pattern = f"%{term}%"
    alternatives: list[ColumnElement[bool]] = [
        _title_prefix_condition(term),
        CatalogItem.catalog_km.ilike(pattern),
        CatalogItem.catalog_uc.ilike(pattern),
        CatalogItem.catalog_numista.ilike(pattern),
        Country.name_original.ilike(pattern),
        Country.name_uk.ilike(pattern),
        Country.name_en.ilike(pattern),
    ]
    if term.isdigit() and len(term) == 4:
        alternatives.append(CatalogItem.issue_year == int(term))
    return or_(*alternatives)


class CatalogRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        is_admin: bool,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._is_admin = is_admin
        self._locale = locale

    # ------------------------------------------------------------ visibility

    def _visible(self) -> ColumnElement[bool]:
        return or_(CatalogItem.created_by.is_(None), CatalogItem.created_by == self._user_id)

    def _snapshot_visible(self) -> ColumnElement[bool]:
        return or_(
            MarketPriceSnapshot.created_by.is_(None),
            MarketPriceSnapshot.created_by == self._user_id,
        )

    def _archive_condition(self, archived: bool) -> ColumnElement[bool]:
        if not archived:
            return not_(CatalogItem.is_archived)
        if self._is_admin:
            return and_(CatalogItem.is_archived)
        # A regular user only sees archived items they hold a coin of.
        return and_(CatalogItem.is_archived, self._own_instance_exists())

    def _own_instance_exists(self) -> ColumnElement[bool]:
        return exists(
            select(CollectionItem.id).where(
                CollectionItem.catalog_item_id == CatalogItem.id,
                CollectionItem.owner_id == self._user_id,
            )
        )

    # --------------------------------------------------------------- listing

    def _filter_conditions(self, filters: CatalogFilters) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            self._visible(),
            self._archive_condition(filters.archived),
            storefront_visible(self._user_id),
        ]
        if filters.scope == "shared":
            conditions.append(CatalogItem.created_by.is_(None))
        elif filters.scope == "own":
            conditions.append(CatalogItem.created_by == self._user_id)
        if filters.country_ids:
            conditions.append(CatalogItem.country_id.in_(filters.country_ids))
        if filters.series_ids:
            conditions.append(CatalogItem.series_id.in_(filters.series_ids))
        if filters.year is not None:
            conditions.append(CatalogItem.issue_year == filters.year)
        if filters.year_from is not None:
            conditions.append(CatalogItem.issue_year >= filters.year_from)
        if filters.year_to is not None:
            conditions.append(CatalogItem.issue_year <= filters.year_to)
        if filters.denomination_ids:
            conditions.append(CatalogItem.denomination_id.in_(filters.denomination_ids))
        if filters.groups:
            conditions.append(CatalogItem.collection_group.in_(filters.groups))
        if filters.material_ids:
            conditions.append(CatalogItem.composition_id.in_(filters.material_ids))
        if filters.owned is True:
            conditions.append(self._own_instance_exists())
        elif filters.owned is False:
            conditions.append(not_(self._own_instance_exists()))
        if filters.q:
            conditions.append(catalog_search_condition(filters.q))
        return conditions

    def _owned_lateral(self) -> Any:
        return (
            select(
                func.coalesce(func.sum(CollectionItem.quantity), 0).label("quantity_owned"),
                func.coalesce(
                    func.sum(
                        CollectionItem.quantity
                        * func.coalesce(CollectionItem.purchase_price, 0)
                        * func.coalesce(CollectionItem.purchase_rate_uah, 1)
                    ),
                    0,
                ).label("purchase_total_uah"),
            )
            .where(
                CollectionItem.catalog_item_id == CatalogItem.id,
                CollectionItem.owner_id == self._user_id,
            )
            .lateral("owned")
        )

    @staticmethod
    def _latest_rate_to_uah() -> Any:
        return (
            select(ExchangeRate.rate_uah)
            .where(ExchangeRate.currency_code == MarketPriceSnapshot.currency_code)
            .order_by(ExchangeRate.effective_date.desc())
            .limit(1)
            .scalar_subquery()
        )

    def _snapshot_price_uah(self) -> ColumnElement[Decimal]:
        """Convert a snapshot to UAH by the latest rate (docs/04, rule 7)."""
        return case(
            (MarketPriceSnapshot.currency_code == "UAH", MarketPriceSnapshot.price),
            else_=MarketPriceSnapshot.price * func.coalesce(self._latest_rate_to_uah(), 0),
        )

    def _price_lateral(self) -> Any:
        """The latest snapshot visible to the user; suspect ones never count."""
        return (
            select(
                self._snapshot_price_uah().label("price_uah"),
                MarketPriceSnapshot.source.label("price_source"),
                MarketPriceSnapshot.observed_at.label("price_observed_at"),
            )
            .where(
                MarketPriceSnapshot.catalog_item_id == CatalogItem.id,
                not_(MarketPriceSnapshot.is_suspect),
                self._snapshot_visible(),
            )
            .order_by(MarketPriceSnapshot.observed_at.desc(), MarketPriceSnapshot.id.desc())
            .limit(1)
            .lateral("latest_price")
        )

    def _country_name(self) -> ColumnElement[str]:
        return localized(
            self._locale, uk=Country.name_uk, en=Country.name_en, original=Country.name_original
        )

    def _material_name(self) -> ColumnElement[str | None]:
        """What the listing shows in "Матеріал": the dictionary name in the
        reader's language, and the record's own free text where the dictionary
        has no row for it (docs/08-ui-map.md)."""
        name = Material.name_uk if self._locale == LOCALE_UK else Material.name_en
        return func.coalesce(name, CatalogItem.material)

    def _series_name(self) -> ColumnElement[str]:
        return localized(
            self._locale,
            uk=CoinSeries.name_uk,
            en=CoinSeries.name_en,
            original=CoinSeries.name_original,
        )

    @staticmethod
    def _source_url_subquery() -> ColumnElement[str | None]:
        """The card's "source" link, preferring UA-Coins over the NBU.

        UA-Coins keeps the coin's page URL in external_id, so its row is the
        link we want. The NBU keeps a card id instead, and no clickable URL is
        built from that, so an NBU row deliberately yields nothing: it is
        ranked above the rest only to outvote the leftover uCoin rows, which
        are legacy and half of them carry the wrong source label. No link beats
        a uCoin link.
        """
        return (
            select(case((PriceSourceLink.source == "NBU", None), else_=PriceSourceLink.external_id))
            .where(PriceSourceLink.catalog_item_id == CatalogItem.id)
            .order_by(
                case(
                    (PriceSourceLink.source == "UA-Coins", 0),
                    (PriceSourceLink.source == "NBU", 1),
                    else_=2,
                ),
                PriceSourceLink.id.desc(),
            )
            .limit(1)
            .scalar_subquery()
        )

    def _order_by(self, filters: CatalogFilters, owned: Any, price: Any) -> list[Any]:
        descending = filters.order == "desc"

        def direction(column: ColumnElement[Any]) -> UnaryExpression[Any]:
            return column.desc().nulls_last() if descending else column.asc().nulls_last()

        by_sort: dict[str, list[Any]] = {
            "title": [_display_title(self._locale)],
            "country": [self._country_name()],
            "series": [self._series_name()],
            "year": [CatalogItem.issue_year],
            "denomination": [Denomination.sort_order, Denomination.value],
            "material": [self._material_name()],
            "owned": [owned.c.quantity_owned],
            "purchase": [owned.c.purchase_total_uah],
            "price": [price.c.price_uah],
        }
        columns = by_sort.get(filters.sort, by_sort["title"])
        ordering: list[Any] = [direction(column) for column in columns]
        # Stable tiebreakers, mirroring the legacy default listing order.
        if filters.sort == "country":
            ordering += [CatalogItem.issue_year.desc(), _display_title(self._locale)]
        ordering.append(CatalogItem.id)
        return ordering

    async def list_items(self, filters: CatalogFilters, *, limit: int, offset: int) -> CatalogPage:
        conditions = self._filter_conditions(filters)

        count_query = (
            select(func.count(CatalogItem.id))
            .join(Country, Country.id == CatalogItem.country_id)
            .where(*conditions)
        )
        total = (await self._session.execute(count_query)).scalar_one()

        owned = self._owned_lateral()
        price = self._price_lateral()
        query = (
            select(
                CatalogItem,
                self._country_name().label("country"),
                self._series_name().label("series_name"),
                Denomination,
                Material,
                owned.c.quantity_owned,
                owned.c.purchase_total_uah,
                price.c.price_uah,
                price.c.price_source,
                price.c.price_observed_at,
                self._source_url_subquery().label("source_url"),
            )
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
            .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
            .outerjoin(Material, Material.id == CatalogItem.composition_id)
            .outerjoin(owned, true())
            .outerjoin(price, true())
            .where(*conditions)
            .order_by(*self._order_by(filters, owned, price))
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        rows = [
            CatalogRow(
                item=row.CatalogItem,
                country=row.country,
                series_name=row.series_name,
                denomination=row.Denomination,
                composition=row.Material,
                quantity_owned=int(row.quantity_owned or 0),
                purchase_total_uah=Decimal(row.purchase_total_uah or 0),
                market_price_uah=row.price_uah,
                price_source=row.price_source,
                price_observed_at=row.price_observed_at,
                source_url=row.source_url,
            )
            for row in result
        ]
        return CatalogPage(rows=rows, total=total)

    # ----------------------------------------------------------------- cards

    async def get_row(self, item_id: int) -> CatalogRow | None:
        """One item with the same computed fields as the listing.

        Archived items stay reachable for an admin and for a user holding a
        coin of the item; for everyone else the card does not exist (404).
        """
        owned = self._owned_lateral()
        price = self._price_lateral()
        query = (
            select(
                CatalogItem,
                self._country_name().label("country"),
                self._series_name().label("series_name"),
                Denomination,
                Material,
                EdgeType,
                QualityType,
                owned.c.quantity_owned,
                owned.c.purchase_total_uah,
                price.c.price_uah,
                price.c.price_source,
                price.c.price_observed_at,
                self._source_url_subquery().label("source_url"),
            )
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
            .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
            .outerjoin(Material, Material.id == CatalogItem.composition_id)
            .outerjoin(EdgeType, EdgeType.id == CatalogItem.edge_type_id)
            .outerjoin(QualityType, QualityType.id == CatalogItem.quality_type_id)
            .outerjoin(owned, true())
            .outerjoin(price, true())
            .where(
                CatalogItem.id == item_id,
                self._visible(),
                or_(
                    not_(CatalogItem.is_archived),
                    true() if self._is_admin else self._own_instance_exists(),
                ),
            )
        )
        row = (await self._session.execute(query)).first()
        if row is None:
            return None
        return CatalogRow(
            item=row.CatalogItem,
            country=row.country,
            series_name=row.series_name,
            denomination=row.Denomination,
            composition=row.Material,
            edge_type=row.EdgeType,
            quality_type=row.QualityType,
            quantity_owned=int(row.quantity_owned or 0),
            purchase_total_uah=Decimal(row.purchase_total_uah or 0),
            market_price_uah=row.price_uah,
            price_source=row.price_source,
            price_observed_at=row.price_observed_at,
            source_url=row.source_url,
        )

    async def year_bounds_by_country(self) -> dict[int, tuple[int, int]]:
        """`(min issue_year, max issue_year)` per country, over the same
        scope a default (non-archived) listing would show — feeds the year
        filter's dropdown bounds (docs/03-api-contract.md)."""
        query = (
            select(
                CatalogItem.country_id,
                func.min(CatalogItem.issue_year),
                func.max(CatalogItem.issue_year),
            )
            .where(
                self._visible(),
                self._archive_condition(archived=False),
                storefront_visible(self._user_id),
            )
            .group_by(CatalogItem.country_id)
        )
        result = await self._session.execute(query)
        return {row[0]: (row[1], row[2]) for row in result}

    async def list_confirmed_materials(self, country_id: int | None = None) -> Sequence[Material]:
        """Materials actually used by a `catalog_confirmed` catalog item —
        the catalog's material filter offers only what could possibly match,
        not the whole shared dictionary (materials have no country_id of
        their own, so this always goes through catalog_items)."""
        condition: ColumnElement[bool] = CatalogItem.composition_id == Material.id
        if country_id is not None:
            condition = and_(condition, CatalogItem.country_id == country_id)
        query = (
            select(Material)
            .where(
                exists(
                    select(CatalogItem.id).where(
                        condition,
                        self._visible(),
                        self._archive_condition(archived=False),
                        storefront_visible(self._user_id),
                    )
                )
            )
            .order_by(Material.name_uk if self._locale == LOCALE_UK else Material.name_en)
        )
        return (await self._session.execute(query)).scalars().all()

    async def get_visible(self, item_id: int) -> CatalogItem | None:
        """The bare item under the visibility filter, archive state ignored.

        For write paths: permissions (403 vs 404 vs archive checks) are the
        service's business, invisibility is the repository's.
        """
        query = select(CatalogItem).where(CatalogItem.id == item_id, self._visible())
        return (await self._session.execute(query)).scalar_one_or_none()

    # ---------------------------------------------------------------- prices

    async def list_prices(self, item_id: int) -> list[Any]:
        """Visible price history, suspect snapshots included but flagged."""
        query = (
            select(
                MarketPriceSnapshot,
                self._snapshot_price_uah().label("price_uah"),
            )
            .where(
                MarketPriceSnapshot.catalog_item_id == item_id,
                self._snapshot_visible(),
            )
            .order_by(MarketPriceSnapshot.observed_at.desc(), MarketPriceSnapshot.id.desc())
        )
        return list(await self._session.execute(query))

    # ---------------------------------------------------------------- writes

    async def add(self, item: CatalogItem) -> CatalogItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def count_references(self, item_id: int) -> tuple[int, int]:
        """(collection items, expenses) pointing at the item — any owner."""
        instances = (
            await self._session.execute(
                select(func.count(CollectionItem.id)).where(
                    CollectionItem.catalog_item_id == item_id
                )
            )
        ).scalar_one()
        expenses = (
            await self._session.execute(
                select(func.count(Expense.id)).where(Expense.catalog_item_id == item_id)
            )
        ).scalar_one()
        return instances, expenses

    async def delete(self, item: CatalogItem) -> None:
        await self._session.delete(item)
        await self._session.flush()
