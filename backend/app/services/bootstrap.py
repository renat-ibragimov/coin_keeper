"""Assembling GET /bootstrap: one request that feeds the whole dashboard."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import User, UserSettings
from app.repositories.dashboard import DashboardRepository
from app.schemas.auth import UserOut
from app.schemas.bootstrap import (
    BootstrapOut,
    BreakdownEntry,
    DashboardOut,
    ExchangeRateOut,
    FinanceOut,
    SeriesBreakdownEntry,
    SettingsOut,
)


class BootstrapService:
    def __init__(self, session: AsyncSession, user: User, locale: str = DEFAULT_LOCALE) -> None:
        self._session = session
        self._user = user
        self._repo = DashboardRepository(session, user_id=user.id, locale=locale)

    async def bootstrap(self) -> BootstrapOut:
        data = await self._repo.dashboard()
        countries = await self._repo.country_breakdown()
        series = await self._repo.series_breakdown()
        finance = await self._repo.finance()
        rates = await self._repo.latest_rates()
        settings = await self._settings()

        missing = max(0, data.catalog_items - data.completed_items)
        percent = (
            0.0
            if data.catalog_items == 0
            else round(data.completed_items / data.catalog_items * 100, 1)
        )

        dashboard = DashboardOut(
            catalog_items=data.catalog_items,
            collection_items=data.collection_items,
            countries=data.countries,
            completed_items=data.completed_items,
            missing_items=missing,
            completion_percent=percent,
            coin_spend_uah=data.coin_spend_uah,
            related_spend_uah=data.related_spend_uah,
            total_spend_uah=data.coin_spend_uah + data.related_spend_uah,
            market_value_uah=data.market_value_uah,
            missing_budget_uah=data.missing_budget_uah,
            unpriced_missing_items=data.unpriced_missing_items,
            country_breakdown=[
                BreakdownEntry(name=row.name, count=row.count, owned=row.owned) for row in countries
            ],
            series_breakdown=[
                SeriesBreakdownEntry(
                    name=row.name, country=row.country or "", count=row.count, owned=row.owned
                )
                for row in series
            ],
            # Empty means "this user has nothing yet": no coins and no
            # personal items. The shared catalog alone does not make a
            # dashboard non-empty — a fresh user sees the empty state.
            is_empty=data.collection_items == 0 and data.personal_items == 0,
        )
        return BootstrapOut(
            user=UserOut.model_validate(self._user),
            settings=settings,
            dashboard=dashboard,
            exchange_rates=[
                ExchangeRateOut(code=row.code, rate=row.rate, effective_date=row.effective_date)
                for row in rates
            ],
            finance=FinanceOut(
                coin_spend_uah=finance.coin_spend_uah,
                coin_spend_usd_at_purchase=(
                    finance.coin_spend_usd_at_purchase
                    if finance.coin_spend_uah
                    else finance.coin_spend_uah
                ),
                coin_spend_eur_at_purchase=(
                    finance.coin_spend_eur_at_purchase
                    if finance.coin_spend_uah
                    else finance.coin_spend_uah
                ),
                purchases_without_historical_usd_rate=finance.purchases_without_usd_rate,
                purchases_without_historical_eur_rate=finance.purchases_without_eur_rate,
            ),
        )

    async def _settings(self) -> SettingsOut:
        row = (
            await self._session.execute(
                select(UserSettings).where(UserSettings.user_id == self._user.id)
            )
        ).scalar_one_or_none()
        if row is None:
            return SettingsOut(
                locale=self._user.locale,
                display_currency="UAH",
                default_grade_commemorative="UNC",
                default_grade_circulation="VF",
            )
        return SettingsOut(
            locale=row.locale,
            display_currency=row.display_currency,
            default_grade_commemorative=row.default_grade_commemorative,
            default_grade_circulation=row.default_grade_circulation,
        )
