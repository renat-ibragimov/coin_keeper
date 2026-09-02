"""Catalog reading: visibility, filters, search, sorting, prices."""

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
    """Reference data plus two verified users, A and B."""
    refs = await seed_reference(db_session)
    email_a, token_a = await register_and_verify(client, mail_outbox)
    email_b, token_b = await register_and_verify(client, mail_outbox)
    return SimpleNamespace(
        refs=refs,
        email_a=email_a,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        email_b=email_b,
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def test_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/catalog")
    assert response.status_code == 401


async def test_listing_shape_and_pagination(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    for year in range(2000, 2005):
        await make_catalog_item(db_session, country=refs.ukraine, title=f"Монета {year}", year=year)

    response = await client.get(
        "/api/v1/catalog?page=2&pageSize=2&sort=year", headers=auth(ctx.token_a)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["pageSize"] == 2
    assert [item["year"] for item in body["items"]] == [2002, 2003]

    first = body["items"][0]
    assert first["title"] == "Монета 2002"
    assert first["country"] == "Україна"
    assert first["isOwn"] is False
    assert first["isArchived"] is False
    assert first["quantityOwned"] == 0
    assert first["purchaseTotalUah"] == "0.00"
    assert first["marketPriceUah"] is None


async def test_personal_items_are_isolated(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    shared = await make_catalog_item(db_session, country=refs.ukraine, title="Спільна", year=2020)
    personal_b = await make_catalog_item(
        db_session, country=refs.ukraine, title="Особиста Б", year=2021, created_by=ctx.id_b
    )

    listing_a = await client.get("/api/v1/catalog", headers=auth(ctx.token_a))
    ids_a = {item["id"] for item in listing_a.json()["items"]}
    assert shared.id in ids_a
    assert personal_b.id not in ids_a

    direct = await client.get(f"/api/v1/catalog/{personal_b.id}", headers=auth(ctx.token_a))
    assert direct.status_code == 404

    listing_b = await client.get("/api/v1/catalog", headers=auth(ctx.token_b))
    own_row = next(item for item in listing_b.json()["items"] if item["id"] == personal_b.id)
    assert own_row["isOwn"] is True


async def test_scope_filter(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    shared = await make_catalog_item(db_session, country=refs.ukraine, title="Спільна", year=2020)
    own = await make_catalog_item(
        db_session, country=refs.ukraine, title="Своя", year=2021, created_by=ctx.id_a
    )

    only_shared = await client.get("/api/v1/catalog?scope=shared", headers=auth(ctx.token_a))
    assert {i["id"] for i in only_shared.json()["items"]} == {shared.id}

    only_own = await client.get("/api/v1/catalog?scope=own", headers=auth(ctx.token_a))
    assert {i["id"] for i in only_own.json()["items"]} == {own.id}


async def test_filters(client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace) -> None:
    refs = ctx.refs
    ua = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Дельфін",
        year=2018,
        denomination=refs.uah_2,
        series=refs.fauna,
    )
    await make_catalog_item(
        db_session, country=refs.usa, title="Lincoln cent", year=2009, denomination=refs.cent_1
    )
    owned_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Київ", year=2020, series=refs.cities
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_item, price="100")

    headers = auth(ctx.token_a)

    by_country = await client.get(f"/api/v1/catalog?countryId={refs.ukraine.id}", headers=headers)
    assert by_country.json()["total"] == 2

    by_series = await client.get(f"/api/v1/catalog?seriesId={refs.fauna.id}", headers=headers)
    assert [i["id"] for i in by_series.json()["items"]] == [ua.id]

    by_year_range = await client.get("/api/v1/catalog?yearFrom=2010&yearTo=2019", headers=headers)
    assert [i["id"] for i in by_year_range.json()["items"]] == [ua.id]

    by_denomination = await client.get(
        f"/api/v1/catalog?denominationId={refs.uah_2.id}", headers=headers
    )
    assert [i["id"] for i in by_denomination.json()["items"]] == [ua.id]

    owned_only = await client.get("/api/v1/catalog?owned=true", headers=headers)
    assert [i["id"] for i in owned_only.json()["items"]] == [owned_item.id]

    missing_only = await client.get("/api/v1/catalog?owned=false", headers=headers)
    assert owned_item.id not in {i["id"] for i in missing_only.json()["items"]}
    assert missing_only.json()["total"] == 2

    # B has no coins: for them the same item is not owned.
    owned_b = await client.get("/api/v1/catalog?owned=true", headers=auth(ctx.token_b))
    assert owned_b.json()["total"] == 0


async def test_search(client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace) -> None:
    refs = ctx.refs
    dolphin = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Дельфін",
        year=2018,
        title_uk="Дельфін",
        catalog_km="KM# 123",
    )
    await make_catalog_item(db_session, country=refs.ukraine, title="Київ", year=2020)
    cent = await make_catalog_item(db_session, country=refs.usa, title="Lincoln cent", year=1914)

    headers = auth(ctx.token_a)

    by_title = await client.get("/api/v1/catalog?q=дельфін", headers=headers)
    assert [i["id"] for i in by_title.json()["items"]] == [dolphin.id]

    by_number = await client.get("/api/v1/catalog?q=KM%23%20123", headers=headers)
    assert [i["id"] for i in by_number.json()["items"]] == [dolphin.id]

    by_country = await client.get("/api/v1/catalog?q=США", headers=headers)
    assert [i["id"] for i in by_country.json()["items"]] == [cent.id]

    by_year = await client.get("/api/v1/catalog?q=1914", headers=headers)
    assert [i["id"] for i in by_year.json()["items"]] == [cent.id]


async def test_archived_visibility(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    active = await make_catalog_item(db_session, country=refs.ukraine, title="Активна", year=2020)
    archived_owned = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Архівна з монетою",
        year=2019,
        is_archived=True,
        archive_reason="duplicate",
    )
    archived_other = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Архівна чужа",
        year=2018,
        is_archived=True,
        archive_reason="withdrawn",
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=archived_owned, price="50")
    await promote_to_admin(db_session, ctx.email_b)
    active_id, owned_id, other_id = active.id, archived_owned.id, archived_other.id

    headers_a = auth(ctx.token_a)

    default_listing = await client.get("/api/v1/catalog", headers=headers_a)
    assert {i["id"] for i in default_listing.json()["items"]} == {active_id}

    archived_a = await client.get("/api/v1/catalog?archived=true", headers=headers_a)
    rows = archived_a.json()["items"]
    assert {i["id"] for i in rows} == {owned_id}
    assert rows[0]["isArchived"] is True
    assert rows[0]["archiveReason"] == "duplicate"

    archived_admin = await client.get("/api/v1/catalog?archived=true", headers=auth(ctx.token_b))
    assert {i["id"] for i in archived_admin.json()["items"]} == {owned_id, other_id}

    # The card of an archived item follows the same rule.
    card_owned = await client.get(f"/api/v1/catalog/{owned_id}", headers=headers_a)
    assert card_owned.status_code == 200
    card_other = await client.get(f"/api/v1/catalog/{other_id}", headers=headers_a)
    assert card_other.status_code == 404
    card_admin = await client.get(f"/api/v1/catalog/{other_id}", headers=auth(ctx.token_b))
    assert card_admin.status_code == 200


async def test_market_price_visibility_and_suspect(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(db_session, country=refs.ukraine, title="Дельфін", year=2018)
    await add_snapshot(db_session, item, "100.00", observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    # B's own snapshot is newer, but only B sees it.
    await add_snapshot(
        db_session,
        item,
        "150.00",
        observed_at=datetime(2026, 2, 1, tzinfo=UTC),
        created_by=ctx.id_b,
        source="Manual",
    )
    # A suspect snapshot is even newer and must never win.
    await add_snapshot(
        db_session,
        item,
        "99999.00",
        observed_at=datetime(2026, 3, 1, tzinfo=UTC),
        is_suspect=True,
    )

    listing_a = await client.get("/api/v1/catalog", headers=auth(ctx.token_a))
    assert listing_a.json()["items"][0]["marketPriceUah"] == "100.00"

    listing_b = await client.get("/api/v1/catalog", headers=auth(ctx.token_b))
    assert listing_b.json()["items"][0]["marketPriceUah"] == "150.00"

    history_a = (
        await client.get(f"/api/v1/catalog/{item.id}/prices", headers=auth(ctx.token_a))
    ).json()
    # A sees the shared snapshot and the suspect one (flagged), not B's.
    assert [row["price"] for row in history_a] == ["99999.00", "100.00"]
    assert history_a[0]["isSuspect"] is True
    assert all(row["isOwn"] is False for row in history_a)

    history_b = (
        await client.get(f"/api/v1/catalog/{item.id}/prices", headers=auth(ctx.token_b))
    ).json()
    assert [row["price"] for row in history_b] == ["99999.00", "150.00", "100.00"]
    own_row = next(row for row in history_b if row["price"] == "150.00")
    assert own_row["isOwn"] is True


async def test_per_user_sorting(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    cheap = await make_catalog_item(db_session, country=refs.ukraine, title="Дешева", year=2001)
    dear = await make_catalog_item(db_session, country=refs.ukraine, title="Дорога", year=2002)
    plain = await make_catalog_item(db_session, country=refs.ukraine, title="Без цін", year=2003)

    await add_snapshot(db_session, cheap, "10.00")
    await add_snapshot(db_session, dear, "500.00")

    # A holds two of the cheap coin and one dear one; B holds only the dear one.
    await add_collection_item(db_session, owner_id=ctx.id_a, item=cheap, quantity=2, price="20")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=dear, price="450")
    await add_collection_item(db_session, owner_id=ctx.id_b, item=dear, price="700")

    async def ids(token: str, sort: str, order: str) -> list[int]:
        response = await client.get(
            f"/api/v1/catalog?sort={sort}&order={order}", headers=auth(token)
        )
        return [row["id"] for row in response.json()["items"]]

    assert await ids(ctx.token_a, "owned", "desc") == [cheap.id, dear.id, plain.id]
    assert await ids(ctx.token_b, "owned", "desc") == [dear.id, cheap.id, plain.id]

    # Purchase totals: A spent 2 x 20 = 40 on cheap and 450 on dear.
    assert await ids(ctx.token_a, "purchase", "desc") == [dear.id, cheap.id, plain.id]
    assert await ids(ctx.token_b, "purchase", "desc") == [dear.id, cheap.id, plain.id]

    assert await ids(ctx.token_a, "price", "desc") == [dear.id, cheap.id, plain.id]
    assert await ids(ctx.token_a, "price", "asc") == [cheap.id, dear.id, plain.id]

    listing = await client.get(
        "/api/v1/catalog?sort=purchase&order=desc", headers=auth(ctx.token_a)
    )
    totals = {row["id"]: row["purchaseTotalUah"] for row in listing.json()["items"]}
    assert totals[cheap.id] == "40.00"
    assert totals[dear.id] == "450.00"


async def test_card_and_own_instances(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Дельфін",
        year=2018,
        denomination=refs.uah_2,
        series=refs.fauna,
        material="нейзильбер",
        catalog_km="KM# 123",
    )
    await add_collection_item(
        db_session, owner_id=ctx.id_a, item=item, quantity=1, price="666", rate_uah="1"
    )

    card = (await client.get(f"/api/v1/catalog/{item.id}", headers=auth(ctx.token_a))).json()
    assert card["title"] == "Дельфін"
    assert card["countryId"] == refs.ukraine.id
    assert card["seriesName"] == "Флора і фауна"
    assert card["denomination"] == "2 гривні"
    assert card["catalogNumber"] == "KM# 123"
    assert card["quantityOwned"] == 1
    assert card["purchaseTotalUah"] == "666.00"

    instances = (
        await client.get(f"/api/v1/catalog/{item.id}/collection-items", headers=auth(ctx.token_a))
    ).json()
    assert len(instances) == 1
    assert instances[0]["purchasePrice"] == "666.00"
    assert instances[0]["totalUah"] == "666.00"

    # B has no instances of it.
    instances_b = (
        await client.get(f"/api/v1/catalog/{item.id}/collection-items", headers=auth(ctx.token_b))
    ).json()
    assert instances_b == []


async def test_snapshot_in_foreign_currency_converted(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    from datetime import date

    from tests.seed import add_rate

    refs = ctx.refs
    item = await make_catalog_item(db_session, country=refs.usa, title="Morgan dollar", year=1921)
    await add_rate(db_session, "USD", "41.50", date(2026, 8, 1))
    await add_rate(db_session, "USD", "40.00", date(2026, 7, 1))
    await add_snapshot(db_session, item, "100.00", currency="USD")

    listing = await client.get("/api/v1/catalog", headers=auth(ctx.token_a))
    row = next(r for r in listing.json()["items"] if r["id"] == item.id)
    # Converted by the latest rate: 100 x 41.50.
    assert row["marketPriceUah"] == "4150.00"


async def test_image_visibility_by_provenance(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """uCoin images are only shown to their importer; nbu ones to everyone."""
    from app.models import MediaFile
    from app.models.enums import MediaRole, MediaSource

    refs = ctx.refs
    ucoin_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018
    )
    nbu_item = await make_catalog_item(db_session, country=refs.ukraine, title="Київ", year=2020)
    db_session.add(
        MediaFile(
            catalog_item_id=ucoin_item.id,
            owner_id=ctx.id_a,
            role=MediaRole.OBVERSE,
            source=MediaSource.UCOIN,
            external_url="https://i.ucoin.net/coin/dolphin-obverse.jpg",
        )
    )
    db_session.add(
        MediaFile(
            catalog_item_id=nbu_item.id,
            role=MediaRole.OBVERSE,
            source=MediaSource.NBU,
            storage_key="catalog/1/obverse/official.webp",
        )
    )
    await db_session.commit()
    ucoin_id, nbu_id = ucoin_item.id, nbu_item.id

    rows_a = {
        row["id"]: row
        for row in (await client.get("/api/v1/catalog", headers=auth(ctx.token_a))).json()["items"]
    }
    # The importer sees the hotlink as it is.
    assert rows_a[ucoin_id]["obverseImageUrl"] == "https://i.ucoin.net/coin/dolphin-obverse.jpg"
    # A stored official photo comes back as a presigned URL.
    assert "catalog/1/obverse/official.webp" in rows_a[nbu_id]["obverseImageUrl"]
    assert "Signature=" in rows_a[nbu_id]["obverseImageUrl"]

    rows_b = {
        row["id"]: row
        for row in (await client.get("/api/v1/catalog", headers=auth(ctx.token_b))).json()["items"]
    }
    # For anyone else the uCoin image is a placeholder, the NBU one is public.
    assert rows_b[ucoin_id]["obverseImageUrl"] is None
    assert rows_b[nbu_id]["obverseImageUrl"] is not None
