"""Exchange rate lookups (docs/business-rules.md, rule 6).

Only the table is read here. It is filled by a separate repository,
coin-parser (collector/rates/), the same way UA-Coins prices are
(docs/integrations.md) -- nothing here writes to exchange_rates.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExchangeRate


class RateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rate_on(self, currency_code: str, on_date: date) -> Decimal | None:
        """The last published rate on or before the date — non-banking days
        take the previous banking day's rate."""
        result = await self._session.execute(
            select(ExchangeRate.rate_uah)
            .where(
                ExchangeRate.currency_code == currency_code,
                ExchangeRate.effective_date <= on_date,
            )
            .order_by(ExchangeRate.effective_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest(self, currency_code: str) -> ExchangeRate | None:
        result = await self._session.execute(
            select(ExchangeRate)
            .where(ExchangeRate.currency_code == currency_code)
            .order_by(ExchangeRate.effective_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
