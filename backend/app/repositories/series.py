"""Series data access and the per-series completeness aggregates.

Series are a shared reference: everyone reads all of them. The summary,
however, is per-user — its completeness counts only catalog items visible to
the user, active in both the numerator and the denominator
(docs/04-business-rules.md, rule 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import ColumnElement, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import CatalogItem, CoinSeries, CollectionItem
from app.repositories.catalog import has_visible_price, latest_price_uah_for
from app.repositories.localization import localized


@dataclass
class SeriesSummaryData:
    total: int
    owned: int
    purchase_total_uah: Decimal
    current_value_uah: Decimal
    unpriced_missing: int


class SeriesRepository:
    def __init__(
        self, session: AsyncSession, *, user_id: int, locale: str = DEFAULT_LOCALE
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._locale = locale

    async def list_series(self, country_id: int | None = None) -> Sequence[CoinSeries]:
        query = select(CoinSeries)
        if country_id is not None:
            query = query.where(CoinSeries.country_id == country_id)
        query = query.order_by(
            localized(
                self._locale,
                uk=CoinSeries.name_uk,
                en=CoinSeries.name_en,
                original=CoinSeries.name_original,
            )
        )
        return (await self._session.execute(query)).scalars().all()

    async def get(self, series_id: int) -> CoinSeries | None:
        return await self._session.get(CoinSeries, series_id)

    async def find_by_name(self, country_id: int, name: str) -> CoinSeries | None:
        result = await self._session.execute(
            select(CoinSeries).where(
                CoinSeries.country_id == country_id, CoinSeries.name_original == name
            )
        )
        return result.scalar_one_or_none()

    async def add(self, series: CoinSeries) -> CoinSeries:
        self._session.add(series)
        await self._session.flush()
        return series

    # -------------------------------------------------------------- summary

    def _visible(self) -> ColumnElement[bool]:
        return or_(CatalogItem.created_by.is_(None), CatalogItem.created_by == self._user_id)

    async def summary(self, series_id: int) -> SeriesSummaryData:
        active_in_series = [
            CatalogItem.series_id == series_id,
            self._visible(),
            not_(CatalogItem.is_archived),
        ]

        # Completeness: both sides of the fraction over active visible items.
        # DISTINCT on both counts — the join multiplies rows per instance.
        counts = (
            await self._session.execute(
                select(
                    func.count(CatalogItem.id.distinct()),
                    func.count(CollectionItem.catalog_item_id.distinct()),
                )
                .select_from(CatalogItem)
                .outerjoin(
                    CollectionItem,
                    (CollectionItem.catalog_item_id == CatalogItem.id)
                    & (CollectionItem.owner_id == self._user_id),
                )
                .where(*active_in_series)
            )
        ).one()
        total, owned = int(counts[0] or 0), int(counts[1] or 0)

        # The money side goes over the user's instances; an instance of an
        # archived item still counts (docs/04, rule 10).
        in_series_any_state = [
            CatalogItem.series_id == series_id,
            self._visible(),
        ]
        money = (
            await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            CollectionItem.quantity
                            * func.coalesce(CollectionItem.purchase_price, 0)
                            * func.coalesce(CollectionItem.purchase_rate_uah, 1)
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            CollectionItem.quantity
                            * func.coalesce(
                                latest_price_uah_for(CollectionItem.catalog_item_id, self._user_id),
                                0,
                            )
                        ),
                        0,
                    ),
                )
                .select_from(CollectionItem)
                .join(CatalogItem, CatalogItem.id == CollectionItem.catalog_item_id)
                .where(CollectionItem.owner_id == self._user_id, *in_series_any_state)
            )
        ).one()
        purchase_total, current_value = Decimal(money[0]), Decimal(money[1])

        unpriced_missing = (
            await self._session.execute(
                select(func.count(CatalogItem.id)).where(
                    *active_in_series,
                    ~select(CollectionItem.id)
                    .where(
                        CollectionItem.catalog_item_id == CatalogItem.id,
                        CollectionItem.owner_id == self._user_id,
                    )
                    .exists(),
                    not_(has_visible_price(CatalogItem.id, self._user_id)),
                )
            )
        ).scalar_one()

        return SeriesSummaryData(
            total=total,
            owned=owned,
            purchase_total_uah=purchase_total,
            current_value_uah=current_value,
            unpriced_missing=int(unpriced_missing),
        )
