"""Catalog data access.

Every query in this repository carries the visibility filter
(created_by IS NULL OR created_by = :user_id) and, unless the archive is
explicitly requested, the verbatim `NOT is_archived` predicate that the partial
indexes expect. Routes never assemble these conditions themselves
(docs/07-auth.md, docs/02-data-model.md).
"""

from __future__ import annotations

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
    func,
    not_,
    or_,
    select,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Country,
    Denomination,
    ExchangeRate,
    Expense,
    MarketPriceSnapshot,
    PriceSourceLink,
)
from app.models.enums import CollectionGroup, MetalKind


@dataclass
class CatalogFilters:
    q: str | None = None
    country_id: int | None = None
    series_id: int | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    denomination_id: int | None = None
    group: CollectionGroup | None = None
    metal_kind: MetalKind | None = None
    owned: bool | None = None
    scope: str = "all"  # all | shared | own
    archived: bool = False
    sort: str = "country"
    order: str = "asc"


@dataclass
class CatalogRow:
    item: CatalogItem
    country: str
    series_name: str | None
    denomination: str | None
    quantity_owned: int
    purchase_total_uah: Decimal
    market_price_uah: Decimal | None
    price_source: str | None
    price_observed_at: datetime | None
    source_url: str | None


@dataclass
class CatalogPage:
    rows: list[CatalogRow] = field(default_factory=list)
    total: int = 0


def _display_title() -> ColumnElement[str]:
    """title_uk → title_original; the original is NOT NULL (docs/02-data-model.md)."""
    return func.coalesce(CatalogItem.title_uk, CatalogItem.title_original)


def _search_vector() -> ColumnElement[Any]:
    """Must match the GIN index expression verbatim or the index is not used."""
    joined = (
        func.coalesce(CatalogItem.title_original, "")
        + " "
        + func.coalesce(CatalogItem.title_uk, "")
        + " "
        + func.coalesce(CatalogItem.title_ru, "")
        + " "
        + func.coalesce(CatalogItem.title_en, "")
    )
    return func.to_tsvector("simple", joined)


def catalog_search_condition(q: str) -> ColumnElement[bool]:
    """Full text over titles, plus catalog numbers, country and year.

    Requires Country joined into the query. Shared with the collection listing,
    which searches by the same catalog fields.
    """
    term = q.strip()
    pattern = f"%{term}%"
    alternatives: list[ColumnElement[bool]] = [
        _search_vector().op("@@")(func.plainto_tsquery("simple", term)),
        CatalogItem.catalog_km.ilike(pattern),
        CatalogItem.catalog_uc.ilike(pattern),
        CatalogItem.catalog_numista.ilike(pattern),
        Country.name_original.ilike(pattern),
    ]
    if term.isdigit() and len(term) == 4:
        alternatives.append(CatalogItem.issue_year == int(term))
    return or_(*alternatives)


class CatalogRepository:
    def __init__(self, session: AsyncSession, *, user_id: int, is_admin: bool) -> None:
        self._session = session
        self._user_id = user_id
        self._is_admin = is_admin

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
        ]
        if filters.scope == "shared":
            conditions.append(CatalogItem.created_by.is_(None))
        elif filters.scope == "own":
            conditions.append(CatalogItem.created_by == self._user_id)
        if filters.country_id is not None:
            conditions.append(CatalogItem.country_id == filters.country_id)
        if filters.series_id is not None:
            conditions.append(CatalogItem.series_id == filters.series_id)
        if filters.year is not None:
            conditions.append(CatalogItem.issue_year == filters.year)
        if filters.year_from is not None:
            conditions.append(CatalogItem.issue_year >= filters.year_from)
        if filters.year_to is not None:
            conditions.append(CatalogItem.issue_year <= filters.year_to)
        if filters.denomination_id is not None:
            conditions.append(CatalogItem.denomination_id == filters.denomination_id)
        if filters.group is not None:
            conditions.append(CatalogItem.collection_group == filters.group)
        if filters.metal_kind is not None:
            conditions.append(CatalogItem.metal_kind == filters.metal_kind)
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

    @staticmethod
    def _source_url_subquery() -> ColumnElement[str | None]:
        return (
            select(PriceSourceLink.external_id)
            .where(PriceSourceLink.catalog_item_id == CatalogItem.id)
            .order_by(
                case(
                    (PriceSourceLink.source == "uCoin", 0),
                    (PriceSourceLink.source == "UA-Coins", 1),
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
            "title": [_display_title()],
            "country": [Country.name_original],
            "series": [CoinSeries.name_original],
            "year": [CatalogItem.issue_year],
            "denomination": [Denomination.value_minor_units, Denomination.label_original],
            "owned": [owned.c.quantity_owned],
            "purchase": [owned.c.purchase_total_uah],
            "price": [price.c.price_uah],
        }
        columns = by_sort.get(filters.sort, by_sort["country"])
        ordering: list[Any] = [direction(column) for column in columns]
        # Stable tiebreakers, mirroring the legacy default listing order.
        if filters.sort == "country":
            ordering += [CatalogItem.issue_year.desc(), _display_title()]
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
                Country.name_original.label("country"),
                CoinSeries.name_original.label("series_name"),
                Denomination.label_original.label("denomination"),
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
                denomination=row.denomination,
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
                Country.name_original.label("country"),
                CoinSeries.name_original.label("series_name"),
                Denomination.label_original.label("denomination"),
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
            denomination=row.denomination,
            quantity_owned=int(row.quantity_owned or 0),
            purchase_total_uah=Decimal(row.purchase_total_uah or 0),
            market_price_uah=row.price_uah,
            price_source=row.price_source,
            price_observed_at=row.price_observed_at,
            source_url=row.source_url,
        )

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
