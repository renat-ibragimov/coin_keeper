"""Anonymous storefront queries. No collection, expense or price tables are joined."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Row, Select, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import SQLColumnExpression

from app.core.locale import DEFAULT_LOCALE
from app.models import (
    CatalogItem,
    CoinSeries,
    Country,
    Denomination,
    EdgeType,
    Material,
    QualityType,
)
from app.repositories.catalog import (
    CatalogFilters,
    CatalogPage,
    CatalogRow,
    _display_title,
    catalog_search_condition,
    issue_date_range_condition,
)
from app.repositories.localization import localized, series_display_name


class PublicCatalogRepository:
    def __init__(self, session: AsyncSession, locale: str = DEFAULT_LOCALE) -> None:
        self.session = session
        self.locale = locale

    def conditions(self, filters: CatalogFilters) -> list[SQLColumnExpression[bool]]:
        conditions = [
            CatalogItem.created_by.is_(None),
            CatalogItem.status == "active",
            not_(CatalogItem.is_archived),
            Country.is_active,
            Country.catalog_confirmed,
        ]
        if filters.q:
            conditions.append(catalog_search_condition(filters.q))
        for value, column in (
            (filters.country_ids, CatalogItem.country_id),
            (filters.series_ids, CatalogItem.series_id),
            (filters.denomination_ids, CatalogItem.denomination_id),
            (filters.groups, CatalogItem.collection_group),
            (filters.material_ids, CatalogItem.composition_id),
        ):
            if value:
                conditions.append(column.in_(value))
        if filters.year is not None:
            conditions.append(CatalogItem.issue_year == filters.year)
        if filters.year_from is not None:
            conditions.append(CatalogItem.issue_year >= filters.year_from)
        if filters.year_to is not None:
            conditions.append(CatalogItem.issue_year <= filters.year_to)
        date_condition = issue_date_range_condition(filters.date_from, filters.date_to)
        if date_condition is not None:
            conditions.append(date_condition)
        if not filters.show_packaging_variants:
            conditions.append(CatalogItem.packaging_of_id.is_(None))
        return conditions

    def query(self) -> Select[tuple[CatalogItem, str, str, Denomination, Material]]:
        country = localized(
            self.locale, uk=Country.name_uk, en=Country.name_en, original=Country.name_original
        ).label("country")
        series = series_display_name(self.locale).label("series_name")
        return (
            select(CatalogItem, country, series, Denomination, Material)
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
            .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
            .outerjoin(Material, Material.id == CatalogItem.composition_id)
        )

    @staticmethod
    def row(result: Row[tuple[CatalogItem, str, str, Denomination, Material]]) -> CatalogRow:
        return CatalogRow(
            item=result.CatalogItem,
            country=result.country,
            series_name=result.series_name,
            denomination=result.Denomination,
            composition=result.Material,
            quantity_owned=0,
            purchase_total_uah=Decimal(0),
            purchase_total_usd=None,
            purchase_total_eur=None,
            market_price_uah=None,
            price_source=None,
            price_observed_at=None,
            source_url=None,
        )

    async def list_items(self, filters: CatalogFilters, *, limit: int, offset: int) -> CatalogPage:
        conditions = self.conditions(filters)
        total = (
            await self.session.execute(
                select(func.count(CatalogItem.id))
                .join(Country, Country.id == CatalogItem.country_id)
                .where(*conditions)
            )
        ).scalar_one()
        sort_columns = {
            "title": _display_title(self.locale),
            "country": localized(
                self.locale, uk=Country.name_uk, en=Country.name_en, original=Country.name_original
            ),
            "series": series_display_name(self.locale),
            "year": CatalogItem.issue_year,
            "denomination": Denomination.value,
            "material": localized(
                self.locale, uk=Material.name_uk, en=Material.name_en, original=Material.name_uk
            ),
        }
        column = sort_columns.get(filters.sort, sort_columns["title"])
        ordering = column.desc() if filters.order == "desc" else column.asc()
        result = await self.session.execute(
            self.query()
            .where(*conditions)
            .order_by(ordering, CatalogItem.id)
            .limit(limit)
            .offset(offset)
        )
        return CatalogPage(rows=[self.row(row) for row in result], total=total)

    async def get_row(self, item_id: int) -> CatalogRow | None:
        query = (
            self.query()
            .add_columns(EdgeType, QualityType)
            .outerjoin(EdgeType, EdgeType.id == CatalogItem.edge_type_id)
            .outerjoin(QualityType, QualityType.id == CatalogItem.quality_type_id)
            .where(CatalogItem.id == item_id, *self.conditions(CatalogFilters()))
        )
        result = (await self.session.execute(query)).first()
        if result is None:
            return None
        row = self.row(result)
        row.edge_type = result.EdgeType
        row.quality_type = result.QualityType
        return row

    async def year_bounds_by_country(self) -> dict[int, tuple[int, int]]:
        query = (
            select(
                CatalogItem.country_id,
                func.min(CatalogItem.issue_year),
                func.max(CatalogItem.issue_year),
            )
            .join(Country, Country.id == CatalogItem.country_id)
            .where(*self.conditions(CatalogFilters()))
            .group_by(CatalogItem.country_id)
        )
        return {row[0]: (row[1], row[2]) for row in (await self.session.execute(query))}

    async def list_confirmed_materials(self, country_id: int | None = None) -> list[Material]:
        conditions = self.conditions(
            CatalogFilters(country_ids=[country_id] if country_id else None)
        )
        query = (
            select(Material)
            .where(
                select(CatalogItem.id)
                .join(Country, Country.id == CatalogItem.country_id)
                .where(CatalogItem.composition_id == Material.id, *conditions)
                .exists()
            )
            .order_by(Material.name_uk if self.locale == "uk" else Material.name_en)
        )
        return list((await self.session.execute(query)).scalars().all())
