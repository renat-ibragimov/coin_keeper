"""Series: listing, admin-only creation, the completeness summary."""

from __future__ import annotations

from datetime import UTC, datetime
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
    promote_to_admin,
    seed_reference,
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


async def test_summary_completeness_rules(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    series = refs.fauna

    owned_twice = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=series
    )
    missing_priced = await make_catalog_item(
        db_session, country=refs.ukraine, title="Сова", year=2017, series=series
    )
    missing_unpriced = await make_catalog_item(
        db_session, country=refs.ukraine, title="Рись", year=2016, series=series
    )
    archived_with_coin = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Архівна",
        year=2015,
        series=series,
        is_archived=True,
        archive_reason="duplicate",
    )
    # Personal item of B in the same series: invisible to A entirely.
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Особиста Б",
        year=2014,
        series=series,
        created_by=ctx.id_b,
    )

    # Two instances of one item still count as one completed position.
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_twice, price="100")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_twice, price="120")
    # An instance of the archived item: money counts, completeness does not.
    await add_collection_item(db_session, owner_id=ctx.id_a, item=archived_with_coin, price="80")

    await add_snapshot(db_session, owned_twice, "150.00")
    await add_snapshot(db_session, missing_priced, "200.00")
    await add_snapshot(db_session, archived_with_coin, "500.00")
    # The only snapshot of the unpriced one is suspect: it stays unpriced.
    await add_snapshot(db_session, missing_unpriced, "77777.00", is_suspect=True)

    summary = (
        await client.get(f"/api/v1/series/{series.id}/summary", headers=auth(ctx.token_a))
    ).json()

    # Active visible: owned_twice, missing_priced, missing_unpriced.
    assert summary["total"] == 3
    assert summary["owned"] == 1
    assert summary["missing"] == 2
    assert summary["completionPercent"] == 33.3
    # Money: 100 + 120 for the dolphin, 80 for the archived instance.
    assert summary["purchaseTotalUah"] == "300.00"
    # Value: 2 dolphins x 150 plus the archived coin at 500.
    assert summary["currentValueUah"] == "800.00"
    assert summary["unpricedMissing"] == 1

    # For B the same series counts their own personal item as collectable.
    summary_b = (
        await client.get(f"/api/v1/series/{series.id}/summary", headers=auth(ctx.token_b))
    ).json()
    assert summary_b["total"] == 4
    assert summary_b["owned"] == 0
    assert summary_b["purchaseTotalUah"] == "0.00"


async def test_summary_percent_never_exceeds_100(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Instances on archived items must not inflate the numerator."""
    refs = ctx.refs
    series = refs.cities
    active = await make_catalog_item(
        db_session, country=refs.ukraine, title="Київ", year=2020, series=series
    )
    archived = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Львів",
        year=2019,
        series=series,
        is_archived=True,
        archive_reason="withdrawn",
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=active, price="10")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=archived, price="10")

    summary = (
        await client.get(f"/api/v1/series/{series.id}/summary", headers=auth(ctx.token_a))
    ).json()
    assert summary["total"] == 1
    assert summary["owned"] == 1
    assert summary["completionPercent"] == 100.0


async def test_summary_unknown_series_404(client: AsyncClient, ctx: SimpleNamespace) -> None:
    response = await client.get("/api/v1/series/999999/summary", headers=auth(ctx.token_a))
    assert response.status_code == 404


async def test_own_price_snapshot_feeds_value(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=refs.fauna
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=item, price="100")
    await add_snapshot(db_session, item, "150.00", observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    # A's own newer snapshot overrides the shared one — for A only.
    await add_snapshot(
        db_session,
        item,
        "180.00",
        observed_at=datetime(2026, 2, 1, tzinfo=UTC),
        created_by=ctx.id_a,
        source="Manual",
    )

    summary_a = (
        await client.get(f"/api/v1/series/{refs.fauna.id}/summary", headers=auth(ctx.token_a))
    ).json()
    assert summary_a["currentValueUah"] == "180.00"
