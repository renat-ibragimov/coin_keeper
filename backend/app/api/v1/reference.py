"""Reference endpoints: countries, denominations, currencies (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, RequestLocale
from app.core.locale import pick_name
from app.models.enums import UserRole
from app.reference_data.denominations import render_label
from app.repositories.catalog import CatalogRepository
from app.repositories.reference import ReferenceRepository
from app.schemas.reference import CountryOut, CurrencyOut, DenominationOut

router = APIRouter(tags=["reference"])


@router.get("/countries")
async def list_countries(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    scope: Annotated[Literal["active", "all", "confirmed"], Query()] = "active",
) -> list[CountryOut]:
    """`scope=active` is the storefront; `scope=all` is the personal-item form,
    where the user may enter a coin of any issuer ever; `scope=confirmed` is
    the catalog's own filter panel — a harder, separate gate (§13a).

    `minYear`/`maxYear` are the issue-year bounds of the catalog items
    actually visible to this user in that country (docs/03-api-contract.md) —
    feeds the year filter's dropdown range, not a global catalog fact.
    """
    countries = await ReferenceRepository(session, locale).list_countries(
        active_only=scope == "active", confirmed_only=scope == "confirmed"
    )
    year_bounds = await CatalogRepository(
        session, user_id=user.id, is_admin=user.role == UserRole.ADMIN
    ).year_bounds_by_country()
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
            min_year=year_bounds.get(country.id, (None, None))[0],
            max_year=year_bounds.get(country.id, (None, None))[1],
        )
        for country in countries
    ]


@router.get("/denominations")
async def list_denominations(
    session: DbSession,
    _user: CurrentUser,
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    scope: Annotated[Literal["all", "confirmed"], Query()] = "all",
) -> list[DenominationOut]:
    """`scope=confirmed` is the catalog's own filter panel: only a
    `catalog_confirmed` country's denominations (§13a)."""
    denominations = await ReferenceRepository(session, locale).list_denominations(
        country_id, confirmed_only=scope == "confirmed"
    )
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
