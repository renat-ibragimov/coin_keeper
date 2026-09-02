"""GET /bootstrap payload (docs/03-api-contract.md, legacy BootstrapPayload)."""

from __future__ import annotations

from datetime import date

from app.schemas.auth import UserOut
from app.schemas.base import CamelModel
from app.schemas.common import Money, Rate


class BreakdownEntry(CamelModel):
    name: str
    count: int
    owned: int


class SeriesBreakdownEntry(BreakdownEntry):
    country: str


class DashboardOut(CamelModel):
    catalog_items: int
    collection_items: int
    countries: int
    completed_items: int
    missing_items: int
    completion_percent: float
    coin_spend_uah: Money
    related_spend_uah: Money
    total_spend_uah: Money
    market_value_uah: Money
    missing_budget_uah: Money
    unpriced_missing_items: int
    country_breakdown: list[BreakdownEntry]
    series_breakdown: list[SeriesBreakdownEntry]
    is_empty: bool


class ExchangeRateOut(CamelModel):
    code: str
    rate: Rate | None
    effective_date: date | None


class FinanceOut(CamelModel):
    coin_spend_uah: Money
    coin_spend_usd_at_purchase: Money | None
    coin_spend_eur_at_purchase: Money | None
    purchases_without_historical_usd_rate: int
    purchases_without_historical_eur_rate: int


class SettingsOut(CamelModel):
    locale: str
    display_currency: str
    default_grade_commemorative: str
    default_grade_circulation: str


class BootstrapOut(CamelModel):
    user: UserOut
    settings: SettingsOut
    dashboard: DashboardOut
    exchange_rates: list[ExchangeRateOut]
    finance: FinanceOut
