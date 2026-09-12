"""Read access to shared reference tables.

Reference data is common to everyone (docs/07-auth.md), so unlike the catalog
repositories nothing here is scoped to a user.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import Country, Currency, Denomination
from app.repositories.localization import localized


class ReferenceRepository:
    def __init__(self, session: AsyncSession, locale: str = DEFAULT_LOCALE) -> None:
        self._session = session
        self._locale = locale

    async def list_countries(
        self, *, active_only: bool = True, confirmed_only: bool = False
    ) -> Sequence[Country]:
        """Active countries drive the storefront; the personal-item form asks
        for all of them (docs/04-business-rules.md). `confirmed_only` is the
        catalog's own filter panel — a harder, separate gate (§13a): only a
        `catalog_confirmed` country is worth offering there at all."""
        query = select(Country)
        if confirmed_only:
            query = query.where(Country.catalog_confirmed)
        elif active_only:
            query = query.where(Country.is_active)
        query = query.order_by(
            Country.sort_order,
            localized(
                self._locale,
                uk=Country.name_uk,
                en=Country.name_en,
                original=Country.name_original,
            ),
        )
        return (await self._session.execute(query)).scalars().all()

    async def list_denominations(
        self, country_id: int | None = None, *, confirmed_only: bool = False
    ) -> Sequence[Denomination]:
        query = select(Denomination).where(Denomination.is_active)
        if country_id is not None:
            query = query.where(Denomination.country_id == country_id)
        if confirmed_only:
            query = query.join(Country, Country.id == Denomination.country_id).where(
                Country.catalog_confirmed
            )
        # sort_order is the face value in the currency's smallest unit; value
        # separates units of equal worth (25 cents and a quarter dollar).
        query = query.order_by(Denomination.sort_order, Denomination.value, Denomination.unit)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def list_currencies(self) -> Sequence[Currency]:
        result = await self._session.execute(select(Currency).order_by(Currency.code))
        return result.scalars().all()
