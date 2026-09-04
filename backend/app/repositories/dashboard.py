"""Dashboard and finance aggregates for GET /bootstrap.

The formulas come from the legacy getDashboardSnapshot/getFinanceSummary
(legacy/reference-code/database.ts) with the multi-user filters applied:
owner_id on personal tables, the visibility filter on catalog and snapshots,
and active-only completeness (docs/04-business-rules.md, rules 5, 8, 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Country,
    ExchangeRate,
    Expense,
)
from app.models.enums import ExpenseCategory
from app.repositories.catalog import has_visible_price, latest_price_uah_for
from app.repositories.localization import localized


@dataclass
class DashboardData:
    catalog_items: int
    collection_items: int
    countries: int
    completed_items: int
    coin_spend_uah: Decimal
    related_spend_uah: Decimal
    market_value_uah: Decimal
    missing_budget_uah: Decimal
    unpriced_missing_items: int
    personal_items: int


@dataclass
class BreakdownRow:
    name: str
    country: str | None
    count: int
    owned: int


@dataclass
class FinanceData:
    coin_spend_uah: Decimal
    coin_spend_usd_at_purchase: Decimal | None
    coin_spend_eur_at_purchase: Decimal | None
    purchases_without_usd_rate: int
    purchases_without_eur_rate: int


@dataclass
class RateRow:
    code: str
    rate: Decimal | None
    effective_date: date | None


class DashboardRepository:
    def __init__(
        self, session: AsyncSession, *, user_id: int, locale: str = DEFAULT_LOCALE
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._locale = locale

    def _visible(self) -> ColumnElement[bool]:
        return or_(CatalogItem.created_by.is_(None), CatalogItem.created_by == self._user_id)

    def _visible_active(self) -> list[ColumnElement[bool]]:
        return [self._visible(), not_(CatalogItem.is_archived)]

    def _no_own_instance(self) -> ColumnElement[bool]:
        return (
            ~select(CollectionItem.id)
            .where(
                CollectionItem.catalog_item_id == CatalogItem.id,
                CollectionItem.owner_id == self._user_id,
            )
            .exists()
        )

    async def _scalar(self, query: Select[Any]) -> Any:
        return (await self._session.execute(query)).scalar_one()

    async def dashboard(self) -> DashboardData:
        visible_active = self._visible_active()

        catalog_items = await self._scalar(
            select(func.count(CatalogItem.id)).where(*visible_active)
        )
        countries = await self._scalar(
            select(func.count(CatalogItem.country_id.distinct())).where(*visible_active)
        )
        collection_items = await self._scalar(
            select(func.coalesce(func.sum(CollectionItem.quantity), 0)).where(
                CollectionItem.owner_id == self._user_id
            )
        )
        completed_items = await self._scalar(
            select(func.count(CollectionItem.catalog_item_id.distinct()))
            .select_from(CollectionItem)
            .join(CatalogItem, CatalogItem.id == CollectionItem.catalog_item_id)
            .where(CollectionItem.owner_id == self._user_id, *visible_active)
        )
        personal_items = await self._scalar(
            select(func.count(CatalogItem.id)).where(CatalogItem.created_by == self._user_id)
        )

        amount_uah = Expense.amount * func.coalesce(Expense.rate_uah, 1)
        spend = (
            await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (Expense.category == ExpenseCategory.COIN_PURCHASE, amount_uah),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (Expense.category != ExpenseCategory.COIN_PURCHASE, amount_uah),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                ).where(Expense.owner_id == self._user_id)
            )
        ).one()

        market_value = await self._scalar(
            select(
                func.coalesce(
                    func.sum(
                        CollectionItem.quantity
                        * func.coalesce(
                            latest_price_uah_for(CollectionItem.catalog_item_id, self._user_id),
                            0,
                        )
                    ),
                    0,
                )
            ).where(CollectionItem.owner_id == self._user_id)
        )
        missing_budget = await self._scalar(
            select(
                func.coalesce(
                    func.sum(func.coalesce(latest_price_uah_for(CatalogItem.id, self._user_id), 0)),
                    0,
                )
            ).where(*visible_active, self._no_own_instance())
        )
        unpriced_missing = await self._scalar(
            select(func.count(CatalogItem.id)).where(
                *visible_active,
                self._no_own_instance(),
                not_(has_visible_price(CatalogItem.id, self._user_id)),
            )
        )

        return DashboardData(
            catalog_items=int(catalog_items),
            collection_items=int(collection_items),
            countries=int(countries),
            completed_items=int(completed_items),
            coin_spend_uah=Decimal(spend[0]),
            related_spend_uah=Decimal(spend[1]),
            market_value_uah=Decimal(market_value),
            missing_budget_uah=Decimal(missing_budget),
            unpriced_missing_items=int(unpriced_missing),
            personal_items=int(personal_items),
        )

    def _country_name(self) -> ColumnElement[str]:
        return localized(
            self._locale, uk=Country.name_uk, en=Country.name_en, original=Country.name_original
        )

    def _series_name(self) -> ColumnElement[str]:
        return localized(
            self._locale,
            uk=CoinSeries.name_uk,
            en=CoinSeries.name_en,
            original=CoinSeries.name_original,
        )

    async def country_breakdown(self, limit: int = 6) -> list[BreakdownRow]:
        owned = CollectionItem
        result = await self._session.execute(
            select(
                self._country_name(),
                func.count(CatalogItem.id.distinct()).label("count"),
                func.count(owned.catalog_item_id.distinct()).label("owned"),
            )
            .select_from(CatalogItem)
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(
                owned,
                (owned.catalog_item_id == CatalogItem.id) & (owned.owner_id == self._user_id),
            )
            .where(*self._visible_active())
            # Grouping by the primary key alone: PostgreSQL knows the rest of
            # the row depends on it, and repeating a bound expression in
            # GROUP BY would not match it anyway.
            .group_by(Country.id)
            .order_by(func.count(CatalogItem.id.distinct()).desc(), self._country_name())
            .limit(limit)
        )
        return [
            BreakdownRow(name=row[0], country=None, count=int(row[1]), owned=int(row[2]))
            for row in result
        ]

    async def series_breakdown(self, limit: int = 6) -> list[BreakdownRow]:
        owned = CollectionItem
        result = await self._session.execute(
            select(
                self._series_name(),
                self._country_name(),
                func.count(CatalogItem.id.distinct()).label("count"),
                func.count(owned.catalog_item_id.distinct()).label("owned"),
            )
            .select_from(CatalogItem)
            .join(CoinSeries, CoinSeries.id == CatalogItem.series_id)
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(
                owned,
                (owned.catalog_item_id == CatalogItem.id) & (owned.owner_id == self._user_id),
            )
            .where(*self._visible_active())
            .group_by(CoinSeries.id, Country.id)
            .order_by(func.count(CatalogItem.id.distinct()).desc(), self._series_name())
            .limit(limit)
        )
        return [
            BreakdownRow(name=row[0], country=row[1], count=int(row[2]), owned=int(row[3]))
            for row in result
        ]

    async def finance(self) -> FinanceData:
        def rate_at(code: str) -> Any:
            return (
                select(ExchangeRate.rate_uah)
                .where(
                    ExchangeRate.currency_code == code,
                    ExchangeRate.effective_date <= Expense.expense_date,
                )
                .order_by(ExchangeRate.effective_date.desc())
                .limit(1)
                .scalar_subquery()
            )

        amount_uah = Expense.amount * func.coalesce(Expense.rate_uah, 1)
        usd_rate = rate_at("USD")
        eur_rate = rate_at("EUR")
        row = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(amount_uah), 0),
                    func.sum(case((usd_rate.is_not(None), amount_uah / usd_rate))),
                    func.sum(case((eur_rate.is_not(None), amount_uah / eur_rate))),
                    func.coalesce(func.sum(case((usd_rate.is_(None), 1), else_=0)), 0),
                    func.coalesce(func.sum(case((eur_rate.is_(None), 1), else_=0)), 0),
                ).where(
                    Expense.owner_id == self._user_id,
                    Expense.category == ExpenseCategory.COIN_PURCHASE,
                )
            )
        ).one()
        return FinanceData(
            coin_spend_uah=Decimal(row[0]),
            coin_spend_usd_at_purchase=None if row[1] is None else Decimal(row[1]),
            coin_spend_eur_at_purchase=None if row[2] is None else Decimal(row[2]),
            purchases_without_usd_rate=int(row[3]),
            purchases_without_eur_rate=int(row[4]),
        )

    async def latest_rates(self, codes: tuple[str, ...] = ("USD", "EUR")) -> list[RateRow]:
        rows: list[RateRow] = []
        for code in codes:
            result = (
                await self._session.execute(
                    select(ExchangeRate.rate_uah, ExchangeRate.effective_date)
                    .where(ExchangeRate.currency_code == code)
                    .order_by(ExchangeRate.effective_date.desc())
                    .limit(1)
                )
            ).first()
            if result is None:
                rows.append(RateRow(code=code, rate=None, effective_date=None))
            else:
                rows.append(RateRow(code=code, rate=result[0], effective_date=result[1]))
        return rows
