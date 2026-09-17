"""Reference endpoints: countries, denominations, coin dictionaries, currencies.

Contract: docs/03-api-contract.md.
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Query

from app.api.deps import ClientIp, CurrentUser, DbSession, OptionalCurrentUser, RequestLocale
from app.api.public_rate_limit import enforce_public_read
from app.core import rate_limit
from app.core.locale import LOCALE_UK, pick_name
from app.models.enums import UserRole
from app.reference_data.denominations import render_label
from app.repositories.catalog import CatalogRepository
from app.repositories.reference import ReferenceRepository
from app.schemas.catalog import CoinEdgeType, CoinMaterial, CoinQualityType
from app.schemas.reference import CountryOut, CurrencyOut, DenominationOut

router = APIRouter(tags=["reference"])


class _Named(Protocol):
    """The three coin dictionaries share a shape: id, code and two names."""

    name_uk: str
    name_en: str


def _localised(row: _Named, locale: str) -> str:
    return row.name_uk if locale == LOCALE_UK else row.name_en


@router.get("/countries")
async def list_countries(
    session: DbSession,
    user: OptionalCurrentUser,
    locale: RequestLocale,
    ip: ClientIp,
    scope: Annotated[Literal["active", "all", "confirmed"], Query()] = "active",
) -> list[CountryOut]:
    """`scope=active` is the storefront; `scope=all` is the personal-item form,
    where the user may enter a coin of any issuer ever; `scope=confirmed` is
    the catalog's own filter panel — a harder, separate gate (§13a).

    `minYear`/`maxYear` are the issue-year bounds of the catalog items
    actually visible to this user in that country (docs/03-api-contract.md) —
    feeds the year filter's dropdown range, not a global catalog fact.
    """
    await enforce_public_read(rate_limit.PUBLIC_REFERENCE, user, ip)
    countries = await ReferenceRepository(session, locale).list_countries(
        active_only=scope == "active", confirmed_only=scope == "confirmed"
    )
    if user:
        year_bounds = await CatalogRepository(
            session, user_id=user.id, is_admin=user.role == UserRole.ADMIN
        ).year_bounds_by_country()
    else:
        from app.repositories.public_catalog import PublicCatalogRepository

        year_bounds = await PublicCatalogRepository(session, locale).year_bounds_by_country()
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
            catalog_confirmed=country.catalog_confirmed,
            sort_order=country.sort_order,
            min_year=year_bounds.get(country.id, (None, None))[0],
            max_year=year_bounds.get(country.id, (None, None))[1],
        )
        for country in countries
    ]


@router.get("/denominations")
async def list_denominations(
    session: DbSession,
    user: OptionalCurrentUser,
    locale: RequestLocale,
    ip: ClientIp,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    scope: Annotated[Literal["all", "confirmed"], Query()] = "all",
) -> list[DenominationOut]:
    """`scope=confirmed` is the catalog's own filter panel: only a
    `catalog_confirmed` country's denominations that a catalog item actually
    visible to this user still uses (§13a)."""
    await enforce_public_read(rate_limit.PUBLIC_REFERENCE, user, ip)
    denominations = await ReferenceRepository(session, locale).list_denominations(
        country_id, confirmed_only=scope == "confirmed", user_id=user.id if user else -1
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


@router.get("/materials")
async def list_materials(
    session: DbSession, _user: CurrentUser, locale: RequestLocale
) -> list[CoinMaterial]:
    """The whole composition dictionary behind `compositionId`.

    Read by the "Додати" form, where a coin entered by hand needs a material:
    a dictionary row when one fits, free text when none does. The catalogue's
    own filter uses the narrower `GET /catalog/materials` instead."""
    materials = await ReferenceRepository(session, locale).list_materials()
    return [
        CoinMaterial(id=row.id, code=row.code, name=_localised(row, locale)) for row in materials
    ]


@router.get("/edge-types")
async def list_edge_types(
    session: DbSession, _user: CurrentUser, locale: RequestLocale
) -> list[CoinEdgeType]:
    """The edge dictionary behind `edgeTypeId` (docs/04-business-rules.md, §14)."""
    rows = await ReferenceRepository(session, locale).list_edge_types()
    return [CoinEdgeType(id=row.id, code=row.code, name=_localised(row, locale)) for row in rows]


@router.get("/quality-types")
async def list_quality_types(
    session: DbSession, _user: CurrentUser, locale: RequestLocale
) -> list[CoinQualityType]:
    """The strike-quality dictionary behind `qualityTypeId`."""
    rows = await ReferenceRepository(session, locale).list_quality_types()
    return [CoinQualityType(id=row.id, code=row.code, name=_localised(row, locale)) for row in rows]


@router.get("/currencies")
async def list_currencies(session: DbSession, _user: CurrentUser) -> list[CurrencyOut]:
    currencies = await ReferenceRepository(session).list_currencies()
    return [CurrencyOut.model_validate(currency) for currency in currencies]
