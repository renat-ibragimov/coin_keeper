"""Reference endpoints: countries, denominations, currencies."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import register_and_verify
from tests.seed import (
    make_catalog_item,
    seed_reference,
    set_country_catalog_confirmed,
    user_id_by_email,
)


async def test_reference_endpoints_require_auth(client: AsyncClient) -> None:
    for path in ("/api/v1/countries", "/api/v1/denominations", "/api/v1/currencies"):
        response = await client.get(path)
        assert response.status_code == 401, path


async def test_active_countries_lead_with_ukraine(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    refs = await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)

    response = await client.get("/api/v1/countries", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    rows = response.json()
    # The storefront shows active countries only, Ukraine first (sortOrder 0).
    assert rows[0]["code"] == "UA"
    assert all(row["isActive"] for row in rows)
    assert [row["name"] for row in rows[1:]] == sorted(row["name"] for row in rows[1:])
    ukraine = next(row for row in rows if row["id"] == refs.ukraine.id)
    assert ukraine == {
        "id": refs.ukraine.id,
        "code": "UA",
        "name": "Україна",
        "nameOriginal": "Україна",
        "originalLang": "uk",
        "nameUk": "Україна",
        "nameEn": "Ukraine",
        "collectVariants": False,
        "isActive": True,
        "sortOrder": 0,
        "minYear": None,
        "maxYear": None,
    }


async def test_every_issuer_is_offered_for_a_personal_item(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    """The chips are the active countries; the create form is all of them."""
    await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}

    active = (await client.get("/api/v1/countries", headers=headers)).json()
    every = (await client.get("/api/v1/countries?scope=all", headers=headers)).json()
    assert len(every) > len(active)
    codes = {row["code"] for row in every}
    assert {"PL", "SUHH", "XAUH"} <= codes
    poland = next(row for row in every if row["code"] == "PL")
    assert poland["nameOriginal"] == "Polska"
    assert poland["nameUk"] == "Польща"
    assert poland["isActive"] is False


async def test_names_follow_the_requested_locale(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}

    for locale, expected in (("uk", "Польща"), ("en", "Poland")):
        rows = (
            await client.get(f"/api/v1/countries?scope=all&locale={locale}", headers=headers)
        ).json()
        assert next(row for row in rows if row["code"] == "PL")["name"] == expected

    by_header = (
        await client.get(
            "/api/v1/countries?scope=all", headers={**headers, "Accept-Language": "en-GB,en;q=0.9"}
        )
    ).json()
    assert next(row for row in by_header if row["code"] == "PL")["name"] == "Poland"


async def test_country_year_bounds_span_visible_catalog_items(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    refs = await seed_reference(db_session)
    email, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await user_id_by_email(db_session, email)

    for year in (2005, 2021, 2013):
        await make_catalog_item(db_session, country=refs.ukraine, title=f"Монета {year}", year=year)
    # Archived and not held by this user: excluded from the default (non-archived) bounds.
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Архівна",
        year=1950,
        is_archived=True,
        archive_reason="test",
    )
    # A personal item still counts towards its own country's bounds.
    await make_catalog_item(
        db_session, country=refs.usa, title="Особиста", year=1999, created_by=user_id
    )

    rows = (await client.get("/api/v1/countries?scope=all", headers=headers)).json()
    ukraine = next(row for row in rows if row["id"] == refs.ukraine.id)
    assert (ukraine["minYear"], ukraine["maxYear"]) == (2005, 2021)
    usa = next(row for row in rows if row["id"] == refs.usa.id)
    assert (usa["minYear"], usa["maxYear"]) == (1999, 1999)
    # A country with no visible catalog items at all: null, not zero.
    poland = next(row for row in rows if row["code"] == "PL")
    assert (poland["minYear"], poland["maxYear"]) == (None, None)


async def test_denominations_filtered_by_country(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    refs = await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(
        f"/api/v1/denominations?countryId={refs.ukraine.id}", headers=headers
    )
    assert response.status_code == 200
    rows = response.json()
    assert [row["label"] for row in rows] == ["2 гривні", "5 гривень"]
    assert rows[0]["value"] == "2.000"
    assert rows[0]["unit"] == "hryvnia"
    assert rows[0]["currencyCode"] == "UAH"

    in_english = await client.get(
        f"/api/v1/denominations?countryId={refs.ukraine.id}&locale=en", headers=headers
    )
    assert [row["label"] for row in in_english.json()] == ["2 hryvnias", "5 hryvnias"]

    everything = await client.get("/api/v1/denominations", headers=headers)
    assert len(everything.json()) == 3


async def test_confirmed_scope_is_a_harder_gate_than_active(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    """docs/04-business-rules.md, §13a: `scope=confirmed` is the catalog's
    own filter panel — active but unconfirmed is not enough."""
    refs = await seed_reference(db_session)
    await set_country_catalog_confirmed(db_session, refs.usa, confirmed=False)
    _, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}

    active = await client.get("/api/v1/countries?scope=active", headers=headers)
    assert refs.usa.id in {row["id"] for row in active.json()}

    confirmed = await client.get("/api/v1/countries?scope=confirmed", headers=headers)
    confirmed_ids = {row["id"] for row in confirmed.json()}
    assert refs.ukraine.id in confirmed_ids
    assert refs.usa.id not in confirmed_ids

    denominations = await client.get(
        f"/api/v1/denominations?countryId={refs.usa.id}&scope=confirmed", headers=headers
    )
    assert denominations.json() == []


async def test_currencies(client: AsyncClient, db_session: AsyncSession, mail_outbox: list) -> None:
    await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)

    response = await client.get("/api/v1/currencies", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    codes = [row["code"] for row in response.json()]
    # SUR and UAK come from migration 0003: the Soviet ruble and the karbovanets.
    assert codes == ["EUR", "SUR", "UAH", "UAK", "USD"]
    uah = next(row for row in response.json() if row["code"] == "UAH")
    assert uah == {"code": "UAH", "name": "Hryvnia", "symbol": "₴", "decimalPlaces": 2}
