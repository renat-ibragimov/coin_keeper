"""GET /catalog/summary: the "Каталог" KPI tiles, scoped to the same
filters GET /catalog accepts, except `owned` (docs/ui.md, decided
2026-09-23 -- the tiles show both sides of the coverage ratio no matter
which availability toggle narrows the visible list)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.helpers import register_and_verify
from tests.seed import (
    add_collection_item,
    add_snapshot,
    make_catalog_item,
    seed_reference,
    set_country_catalog_confirmed,
    user_id_by_email,
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ctx(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> SimpleNamespace:
    refs = await seed_reference(db_session)
    email_a, token_a = await register_and_verify(client, mail_outbox)
    return SimpleNamespace(
        refs=refs, token_a=token_a, id_a=await user_id_by_email(db_session, email_a)
    )


async def test_summary_counts_owned_missing_and_money(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    series = refs.fauna

    owned = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=series
    )
    missing_priced = await make_catalog_item(
        db_session, country=refs.ukraine, title="Сова", year=2017, series=series
    )
    missing_unpriced = await make_catalog_item(
        db_session, country=refs.ukraine, title="Рись", year=2016, series=series
    )
    # A different series: excluded once the test filters by `series`.
    other_series_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Місто", year=2019, series=refs.cities
    )

    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned, price="150", quantity=2)
    await add_snapshot(db_session, missing_priced, "80")
    _ = other_series_item

    response = await client.get(
        f"/api/v1/catalog/summary?seriesId={series.id}", headers=auth(ctx.token_a)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["owned"] == 1
    assert body["missing"] == 2
    assert body["purchaseTotalUah"] == "300.00"
    assert body["missingBudgetUah"] == "80.00"
    assert body["unpricedMissing"] == 1

    _ = missing_unpriced


async def test_owned_filter_does_not_change_the_summary(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    owned = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=refs.fauna
    )
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Сова", year=2017, series=refs.fauna
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned, price="150")

    unfiltered = await client.get(
        f"/api/v1/catalog/summary?seriesId={refs.fauna.id}", headers=auth(ctx.token_a)
    )
    owned_only = await client.get(
        f"/api/v1/catalog/summary?seriesId={refs.fauna.id}&owned=true", headers=auth(ctx.token_a)
    )
    missing_only = await client.get(
        f"/api/v1/catalog/summary?seriesId={refs.fauna.id}&owned=false", headers=auth(ctx.token_a)
    )
    bodies = [r.json() for r in (unfiltered, owned_only, missing_only)]
    for body in bodies:
        assert body["total"] == 2
        assert body["owned"] == 1
        assert body["missing"] == 1
        assert body["purchaseTotalUah"] == "150.00"


async def test_country_filter_narrows_the_summary(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    await set_country_catalog_confirmed(db_session, refs.usa, True)
    ukraine_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018
    )
    usa_item = await make_catalog_item(db_session, country=refs.usa, title="Quarter", year=2020)
    await add_collection_item(db_session, owner_id=ctx.id_a, item=ukraine_item, price="100")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=usa_item, price="200")

    ukraine_only = (
        await client.get(
            f"/api/v1/catalog/summary?countryId={refs.ukraine.id}", headers=auth(ctx.token_a)
        )
    ).json()
    assert ukraine_only["total"] == 1
    assert ukraine_only["owned"] == 1
    assert ukraine_only["purchaseTotalUah"] == "100.00"


async def test_summary_requires_a_confirmed_country_like_the_listing(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The unconfirmed country's owned item shows in "Моя колекція" but not
    in the catalog summary -- the same §13a gate `GET /catalog` applies."""
    refs = ctx.refs
    await set_country_catalog_confirmed(db_session, refs.usa, False)
    usa_item = await make_catalog_item(db_session, country=refs.usa, title="Quarter", year=2020)
    await add_collection_item(db_session, owner_id=ctx.id_a, item=usa_item, price="200")

    listing = await client.get(
        f"/api/v1/catalog?countryId={refs.usa.id}", headers=auth(ctx.token_a)
    )
    summary = await client.get(
        f"/api/v1/catalog/summary?countryId={refs.usa.id}", headers=auth(ctx.token_a)
    )
    assert listing.json()["total"] == 0
    assert summary.json()["total"] == 0
    assert summary.json()["owned"] == 0
