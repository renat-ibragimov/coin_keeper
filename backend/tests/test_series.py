"""Series: listing, admin-only creation, the completeness summary."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.helpers import register_and_verify
from tests.seed import (
    add_collection_item,
    make_catalog_item,
    make_series,
    promote_to_admin,
    seed_reference,
    set_country_active,
    set_country_catalog_confirmed,
    user_id_by_email,
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ctx(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> SimpleNamespace:
    """A is a regular user, B is an admin."""
    refs = await seed_reference(db_session)
    email_a, token_a = await register_and_verify(client, mail_outbox)
    email_b, token_b = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, email_b)
    return SimpleNamespace(
        refs=refs,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def test_list_series(client: AsyncClient, ctx: SimpleNamespace) -> None:
    listing = await client.get("/api/v1/series", headers=auth(ctx.token_a))
    assert listing.status_code == 200
    names = [row["name"] for row in listing.json()]
    assert names == ["Міста України", "Флора і фауна"]

    by_country = await client.get(
        f"/api/v1/series?countryId={ctx.refs.usa.id}", headers=auth(ctx.token_a)
    )
    assert by_country.json() == []


async def test_create_series_is_admin_only(client: AsyncClient, ctx: SimpleNamespace) -> None:
    payload = {"countryId": ctx.refs.ukraine.id, "name": "Збройні Сили"}

    denied = await client.post("/api/v1/series", json=payload, headers=auth(ctx.token_a))
    assert denied.status_code == 403

    created = await client.post("/api/v1/series", json=payload, headers=auth(ctx.token_b))
    assert created.status_code == 201
    assert created.json()["name"] == "Збройні Сили"

    duplicate = await client.post("/api/v1/series", json=payload, headers=auth(ctx.token_b))
    assert duplicate.status_code == 409

    bad_country = await client.post(
        "/api/v1/series",
        json={"countryId": 999999, "name": "Немає"},
        headers=auth(ctx.token_b),
    )
    assert bad_country.status_code == 422


async def test_progress_lists_every_series_with_its_summary(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    owned = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=refs.fauna
    )
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Сова", year=2017, series=refs.fauna
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned, price="100.00")

    progress = (
        await client.get(
            f"/api/v1/series/summary?countryId={refs.ukraine.id}", headers=auth(ctx.token_a)
        )
    ).json()
    by_name = {row["series"]["name"]: row["summary"] for row in progress}
    assert by_name[refs.fauna.name_original] == {
        "total": 2,
        "owned": 1,
        "missing": 1,
        "completionPercent": 50.0,
        "purchaseTotalUah": "100.00",
        "currentValueUah": "0.00",
        "unpricedMissing": 1,
    }
    # Every series of the country is listed, even the ones without items.
    assert len(progress) == len(
        (
            await client.get(
                f"/api/v1/series?countryId={refs.ukraine.id}", headers=auth(ctx.token_a)
            )
        ).json()
    )

    other_country = (
        await client.get(
            f"/api/v1/series/summary?countryId={refs.usa.id}", headers=auth(ctx.token_a)
        )
    ).json()
    assert refs.fauna.name_original not in {row["series"]["name"] for row in other_country}


async def test_storefront_hides_series_of_deactivated_country(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """docs/business-rules.md, BR-13: a series of a deactivated country
    disappears from listings unless the user already owns something in it."""
    refs = ctx.refs
    await set_country_active(db_session, refs.usa, active=False)

    series_usa = await make_series(db_session, country=refs.usa, name="Standing Liberty")
    owned_item = await make_catalog_item(
        db_session, country=refs.usa, title="Quarter", year=1920, series=series_usa
    )
    unowned_item = await make_catalog_item(
        db_session, country=refs.usa, title="Dime", year=1921, series=series_usa
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_item, price="10")

    headers_a = auth(ctx.token_a)
    headers_b = auth(ctx.token_b)

    listing_a = await client.get("/api/v1/series", headers=headers_a)
    names_a = {row["name"] for row in listing_a.json()}
    assert series_usa.name_original in names_a

    listing_b = await client.get("/api/v1/series", headers=headers_b)
    names_b = {row["name"] for row in listing_b.json()}
    assert series_usa.name_original not in names_b

    progress_a = (await client.get("/api/v1/series/summary", headers=headers_a)).json()
    by_name_a = {row["series"]["name"]: row["summary"] for row in progress_a}
    assert by_name_a[series_usa.name_original]["total"] == 2
    assert by_name_a[series_usa.name_original]["owned"] == 1

    progress_b = (await client.get("/api/v1/series/summary", headers=headers_b)).json()
    assert series_usa.name_original not in {row["series"]["name"] for row in progress_b}

    _ = unowned_item


async def test_series_of_an_unconfirmed_country_still_shows(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """docs/business-rules.md, BR-13a: the `catalog_confirmed` gate is
    `GET /catalog`-only. The series screens are about the user's own
    collection, so an unconfirmed country's series still shows there when
    the user actually owns something in it (owner's call, 2026-09-12)."""
    refs = ctx.refs
    await set_country_catalog_confirmed(db_session, refs.usa, confirmed=False)

    series_usa = await make_series(db_session, country=refs.usa, name="Standing Liberty")
    owned_item = await make_catalog_item(
        db_session, country=refs.usa, title="Quarter", year=1920, series=series_usa
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_item, price="10")

    headers_a = auth(ctx.token_a)

    listing_a = await client.get("/api/v1/series", headers=headers_a)
    assert series_usa.name_original in {row["name"] for row in listing_a.json()}

    progress_a = (await client.get("/api/v1/series/summary", headers=headers_a)).json()
    assert series_usa.name_original in {row["series"]["name"] for row in progress_a}


async def test_scope_catalog_is_the_confirmed_gate_for_the_series_filter(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """docs/business-rules.md, BR-13a: `GET /series?scope=catalog` backs the
    catalog's own series filter — unlike the default `scope=mine`, an owned
    instance does not let an unconfirmed country's series through."""
    refs = ctx.refs
    await set_country_catalog_confirmed(db_session, refs.usa, confirmed=False)

    series_usa = await make_series(db_session, country=refs.usa, name="Standing Liberty")
    owned_item = await make_catalog_item(
        db_session, country=refs.usa, title="Quarter", year=1920, series=series_usa
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_item, price="10")

    headers_a = auth(ctx.token_a)

    mine = await client.get("/api/v1/series?scope=mine", headers=headers_a)
    assert series_usa.name_original in {row["name"] for row in mine.json()}

    catalog_scope = await client.get("/api/v1/series?scope=catalog", headers=headers_a)
    assert series_usa.name_original not in {row["name"] for row in catalog_scope.json()}
    assert refs.fauna.name_original in {row["name"] for row in catalog_scope.json()}


async def test_is_official_marks_only_a_parser_maintained_series(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """False unless the issuer's own catalogue parser claims the series.

    Nothing backfills the flag (migration 0006): load-series in coin-parser
    raises it for the NBU series it walks, and curated ones stay false.
    """
    from app.models import CoinSeries

    curated = await make_series(db_session, country=ctx.refs.ukraine, name="Добірка колекціонера")
    official = await make_series(
        db_session, country=ctx.refs.ukraine, name="Пам'ятні монети НБУ", is_official=True
    )

    assert (await db_session.get(CoinSeries, curated.id)).is_official is False  # type: ignore[union-attr]
    assert (await db_session.get(CoinSeries, official.id)).is_official is True  # type: ignore[union-attr]
