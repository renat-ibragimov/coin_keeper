"""Reference endpoints: countries, denominations, currencies (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, RequestLocale
from app.core.locale import pick_name
from app.reference_data.denominations import render_label
from app.repositories.reference import ReferenceRepository
from app.schemas.reference import CountryOut, CurrencyOut, DenominationOut

router = APIRouter(tags=["reference"])


@router.get("/countries")
async def list_countries(
    session: DbSession,
    _user: CurrentUser,
    locale: RequestLocale,
    scope: Annotated[Literal["active", "all"], Query()] = "active",
) -> list[CountryOut]:
    """`scope=active` is the storefront; `scope=all` is the personal-item form,
    where the user may enter a coin of any issuer ever."""
    countries = await ReferenceRepository(session, locale).list_countries(
        active_only=scope == "active"
    )
    return [
        CountryOut(
            id=country.id,
            code=country.code,
            name=pick_name(
                locale, uk=country.name_uk, en=country.name_en, original=country.name_original
            ),
            name_original=country.name_original,
            original_lang=country.original_lang,
            name_uk=country.name_uk,
            name_en=country.name_en,
            collect_variants=country.collect_variants,
            is_active=country.is_active,
            sort_order=country.sort_order,
        )
        for country in countries
    ]


@router.get("/denominations")
async def list_denominations(
    session: DbSession,
    _user: CurrentUser,
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[DenominationOut]:
    denominations = await ReferenceRepository(session, locale).list_denominations(country_id)
    return [
        DenominationOut(
            id=denomination.id,
            country_id=denomination.country_id,
            currency_code=denomination.currency_code,
            value=denomination.value,
            unit=denomination.unit,
            label=render_label(denomination.value, denomination.unit, locale),
            sort_order=denomination.sort_order,
        )
        for denomination in denominations
    ]


@router.get("/currencies")
async def list_currencies(session: DbSession, _user: CurrentUser) -> list[CurrencyOut]:
    currencies = await ReferenceRepository(session).list_currencies()
    return [CurrencyOut.model_validate(currency) for currency in currencies]
