"""Reference endpoints: countries, denominations, currencies (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.repositories.reference import ReferenceRepository
from app.schemas.reference import CountryOut, CurrencyOut, DenominationOut

router = APIRouter(tags=["reference"])


@router.get("/countries")
async def list_countries(session: DbSession, _user: CurrentUser) -> list[CountryOut]:
    countries = await ReferenceRepository(session).list_countries()
    return [
        CountryOut(
            id=country.id,
            code=country.code,
            name=country.name_original,
            name_ru=country.name_ru,
            name_en=country.name_en,
            collect_variants=country.collect_variants,
        )
        for country in countries
    ]


@router.get("/denominations")
async def list_denominations(
    session: DbSession,
    _user: CurrentUser,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[DenominationOut]:
    denominations = await ReferenceRepository(session).list_denominations(country_id)
    return [
        DenominationOut(
            id=denomination.id,
            country_id=denomination.country_id,
            currency_code=denomination.currency_code,
            value_minor_units=denomination.value_minor_units,
            label=denomination.label_original,
            label_ru=denomination.label_ru,
            label_en=denomination.label_en,
            sort_order=denomination.sort_order,
        )
        for denomination in denominations
    ]


@router.get("/currencies")
async def list_currencies(session: DbSession, _user: CurrentUser) -> list[CurrencyOut]:
    currencies = await ReferenceRepository(session).list_currencies()
    return [CurrencyOut.model_validate(currency) for currency in currencies]
