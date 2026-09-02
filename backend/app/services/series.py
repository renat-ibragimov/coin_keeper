"""Series use cases.

Series are part of the shared catalog: there are no personal series, and
creating one is an admin operation (docs/03-api-contract.md, docs/04, rule 2).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CoinSeries, Country, User
from app.models.enums import UserRole
from app.repositories.series import SeriesRepository
from app.schemas.series import SeriesCreate, SeriesOut, SeriesSummaryOut


class SeriesError(Exception):
    pass


class SeriesNotFoundError(SeriesError):
    pass


class SeriesForbiddenError(SeriesError):
    """Series are shared reference data; creation needs admin rights: 403."""


class DuplicateSeriesError(SeriesError):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.detail = f"A series named '{name}' already exists for this country."


class UnknownCountryError(SeriesError):
    detail = "Unknown countryId."


def _out(series: CoinSeries) -> SeriesOut:
    return SeriesOut(
        id=series.id,
        country_id=series.country_id,
        name=series.name_original,
        name_ru=series.name_ru,
        name_en=series.name_en,
        description=series.description,
        start_year=series.start_year,
        end_year=series.end_year,
    )


class SeriesService:
    def __init__(self, session: AsyncSession, user: User) -> None:
        self._session = session
        self._user = user
        self._repo = SeriesRepository(session, user_id=user.id)

    async def list_series(self, country_id: int | None) -> list[SeriesOut]:
        return [_out(series) for series in await self._repo.list_series(country_id)]

    async def create(self, payload: SeriesCreate) -> SeriesOut:
        if self._user.role != UserRole.ADMIN:
            raise SeriesForbiddenError
        if await self._session.get(Country, payload.country_id) is None:
            raise UnknownCountryError
        name = payload.name.strip()
        if await self._repo.find_by_name(payload.country_id, name) is not None:
            raise DuplicateSeriesError(name)
        series = CoinSeries(
            country_id=payload.country_id,
            name_original=name,
            description=payload.description,
            start_year=payload.start_year,
            end_year=payload.end_year,
        )
        await self._repo.add(series)
        return _out(series)

    async def summary(self, series_id: int) -> SeriesSummaryOut:
        if await self._repo.get(series_id) is None:
            raise SeriesNotFoundError
        data = await self._repo.summary(series_id)
        percent = 0.0 if data.total == 0 else round(data.owned / data.total * 100, 1)
        return SeriesSummaryOut(
            total=data.total,
            owned=data.owned,
            missing=max(0, data.total - data.owned),
            completion_percent=percent,
            purchase_total_uah=data.purchase_total_uah,
            current_value_uah=data.current_value_uah,
            unpriced_missing=data.unpriced_missing,
        )
