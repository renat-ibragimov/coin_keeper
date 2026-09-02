"""Read access to shared reference tables.

Reference data is common to everyone (docs/07-auth.md), so unlike the catalog
repositories nothing here is scoped to a user.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Country, Currency, Denomination


class ReferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_countries(self) -> Sequence[Country]:
        result = await self._session.execute(
            select(Country).where(Country.is_active).order_by(Country.name_original)
        )
        return result.scalars().all()

    async def list_denominations(self, country_id: int | None = None) -> Sequence[Denomination]:
        query = select(Denomination).where(Denomination.is_active)
        if country_id is not None:
            query = query.where(Denomination.country_id == country_id)
        query = query.order_by(
            Denomination.sort_order,
            Denomination.value_minor_units.nulls_last(),
            Denomination.label_original,
        )
        result = await self._session.execute(query)
        return result.scalars().all()

    async def list_currencies(self) -> Sequence[Currency]:
        result = await self._session.execute(select(Currency).order_by(Currency.code))
        return result.scalars().all()
