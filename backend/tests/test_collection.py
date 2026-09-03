"""Collection CRUD: the purchase transaction, rates, isolation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import CatalogItem, CollectionItem, Expense
from app.models.enums import ExpenseCategory
from tests.helpers import register_and_verify
from tests.seed import (
    add_rate,
    add_snapshot,
    make_catalog_item,
    seed_reference,
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
    email_b, token_b = await register_and_verify(client, mail_outbox)
    item = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Дельфін",
        year=2018,
        denomination=refs.uah_2,
        series=refs.fauna,
    )
    return SimpleNamespace(
        refs=refs,
        item_id=item.id,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def _expense_totals(db_session: AsyncSession, owner_id: int) -> tuple[int, Decimal]:
    result = await db_session.execute(
        select(
            func.count(Expense.id),
            func.coalesce(func.sum(Expense.amount * func.coalesce(Expense.rate_uah, 1)), 0),
        ).where(Expense.owner_id == owner_id, Expense.category == ExpenseCategory.COIN_PURCHASE)
    )
    count, total = result.one()
    return int(count), Decimal(total)


async def test_purchase_creates_expense_in_one_transaction(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    response = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 2,
            "price": "150.50",
            "currency": "UAH",
            "purchaseDate": "2024-03-10",
            "seller": "OLX",
        },
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["price"] == "150.50"
    assert body["rateUah"] == "1"
    assert body["totalUah"] == "301.00"
    assert body["title"] == "Дельфін"

    count, total = await _expense_totals(db_session, ctx.id_a)
    assert count == 1
    assert total == Decimal("301.00")

    expense = (
        await db_session.execute(select(Expense).where(Expense.owner_id == ctx.id_a))
    ).scalar_one()
    assert expense.collection_item_id == body["id"]
    assert expense.catalog_item_id == ctx.item_id
    assert expense.expense_date == date(2024, 3, 10)
    assert expense.vendor == "OLX"


async def test_purchase_in_foreign_currency_takes_rate_on_or_before_date(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await add_rate(db_session, "USD", "26.50", date(2018, 3, 20))
    await add_rate(db_session, "USD", "27.00", date(2018, 3, 23))
    await add_rate(db_session, "USD", "28.00", date(2018, 4, 1))

    response = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "10.00",
            "currency": "USD",
            # 2018-03-24 is not a banking day in the table: the rate of the
            # 23rd applies, never the later one.
            "purchaseDate": "2018-03-24",
        },
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rateUah"] == "27"
    assert body["currency"] == "USD"
    assert body["totalUah"] == "270.00"


async def test_purchase_without_rate_is_422(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await add_rate(db_session, "USD", "27.00", date(2020, 1, 1))

    response = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "10.00",
            "currency": "USD",
            "purchaseDate": "2019-12-31",
        },
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 422
    assert "exchange-rate-missing" in response.json()["type"]

    # Nothing was half-created.
    instances = (
        await db_session.execute(
            select(func.count(CollectionItem.id)).where(CollectionItem.owner_id == ctx.id_a)
        )
    ).scalar_one()
    count, _ = await _expense_totals(db_session, ctx.id_a)
    assert (instances, count) == (0, 0)


async def test_purchase_of_invisible_item_is_404(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    personal_b = await make_catalog_item(
        db_session, country=ctx.refs.ukraine, title="Особиста Б", year=2021, created_by=ctx.id_b
    )
    response = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": personal_b.id,
            "quantity": 1,
            "price": "1.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
        },
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 404


async def test_failure_mid_transaction_leaves_no_half(
    client: AsyncClient,
    db_session: AsyncSession,
    ctx: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.collection import CollectionService

    def broken_expense(self: CollectionService, instance: CollectionItem) -> Expense:
        raise RuntimeError("boom after the instance insert")

    monkeypatch.setattr(CollectionService, "_build_expense", broken_expense)

    with pytest.raises(RuntimeError):
        await client.post(
            "/api/v1/collection",
            json={
                "catalogItemId": ctx.item_id,
                "quantity": 1,
                "price": "100.00",
                "currency": "UAH",
                "purchaseDate": "2024-01-01",
            },
            headers=auth(ctx.token_a),
        )

    instances = (
        await db_session.execute(
            select(func.count(CollectionItem.id)).where(CollectionItem.owner_id == ctx.id_a)
        )
    ).scalar_one()
    count, _ = await _expense_totals(db_session, ctx.id_a)
    assert (instances, count) == (0, 0)


async def test_update_recomputes_expense(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await add_rate(db_session, "USD", "27.00", date(2018, 1, 1))
    headers = auth(ctx.token_a)
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "100.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
        },
        headers=headers,
    )
    item_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/collection/{item_id}",
        json={"quantity": 3, "price": "10.00", "currency": "USD", "purchaseDate": "2018-06-01"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["rateUah"] == "27"
    assert body["totalUah"] == "810.00"

    count, total = await _expense_totals(db_session, ctx.id_a)
    assert count == 1
    assert total == Decimal("810.00")
    expense = (
        await db_session.execute(select(Expense).where(Expense.owner_id == ctx.id_a))
    ).scalar_one()
    assert expense.amount == Decimal("30.00")
    assert expense.currency_code == "USD"
    assert expense.expense_date == date(2018, 6, 1)


async def test_delete_removes_linked_expense(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    headers = auth(ctx.token_a)
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "120.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
        },
        headers=headers,
    )
    item_id = created.json()["id"]
    count, total = await _expense_totals(db_session, ctx.id_a)
    assert (count, total) == (1, Decimal("120.00"))

    deleted = await client.delete(f"/api/v1/collection/{item_id}", headers=headers)
    assert deleted.status_code == 204

    count, total = await _expense_totals(db_session, ctx.id_a)
    assert (count, total) == (0, Decimal(0))


async def test_collection_is_isolated_between_users(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    headers_a = auth(ctx.token_a)
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "50.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
        },
        headers=headers_a,
    )
    item_id = created.json()["id"]

    listing_b = await client.get("/api/v1/collection", headers=auth(ctx.token_b))
    assert listing_b.json()["total"] == 0

    for method, url in (
        ("patch", f"/api/v1/collection/{item_id}"),
        ("delete", f"/api/v1/collection/{item_id}"),
    ):
        response = await client.request(
            method, url, json={"quantity": 5}, headers=auth(ctx.token_b)
        )
        assert response.status_code == 404, (method, url)

    # A's own row is intact.
    listing_a = await client.get("/api/v1/collection", headers=headers_a)
    assert listing_a.json()["total"] == 1
    assert listing_a.json()["items"][0]["quantity"] == 1


async def test_listing_filters_and_sorting(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    cent = await make_catalog_item(
        db_session, country=refs.usa, title="Lincoln cent", year=2009, denomination=refs.cent_1
    )
    headers = auth(ctx.token_a)

    for catalog_item_id, price, purchase_date in (
        (ctx.item_id, "300.00", "2024-01-10"),
        (cent.id, "20.00", "2024-02-15"),
    ):
        response = await client.post(
            "/api/v1/collection",
            json={
                "catalogItemId": catalog_item_id,
                "quantity": 1,
                "price": price,
                "currency": "UAH",
                "purchaseDate": purchase_date,
            },
            headers=headers,
        )
        assert response.status_code == 201

    by_country = await client.get(
        f"/api/v1/collection?countryId={refs.ukraine.id}", headers=headers
    )
    assert by_country.json()["total"] == 1
    assert by_country.json()["items"][0]["title"] == "Дельфін"

    by_series = await client.get(f"/api/v1/collection?seriesId={refs.fauna.id}", headers=headers)
    assert by_series.json()["total"] == 1

    by_q = await client.get("/api/v1/collection?q=lincoln", headers=headers)
    assert by_q.json()["total"] == 1
    assert by_q.json()["items"][0]["title"] == "Lincoln cent"

    newest_first = await client.get("/api/v1/collection?sort=date", headers=headers)
    assert [row["title"] for row in newest_first.json()["items"]] == [
        "Lincoln cent",
        "Дельфін",
    ]

    by_total = await client.get("/api/v1/collection?sort=total&order=desc", headers=headers)
    assert [row["totalUah"] for row in by_total.json()["items"]] == ["300.00", "20.00"]


async def test_get_single_instance_is_owner_only(client: AsyncClient, ctx: SimpleNamespace) -> None:
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "300.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-10",
        },
        headers=auth(ctx.token_a),
    )
    item_id = created.json()["id"]

    own = await client.get(f"/api/v1/collection/{item_id}", headers=auth(ctx.token_a))
    assert own.status_code == 200
    assert own.json()["title"] == "Дельфін"

    foreign = await client.get(f"/api/v1/collection/{item_id}", headers=auth(ctx.token_b))
    assert foreign.status_code == 404


async def test_listing_carries_catalog_context(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The collection screen shows a photo and the current valuation per
    instance without asking the catalog again: the latest visible price and
    the visible thumbnail travel with each row."""
    headers = auth(ctx.token_a)
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 2,
            "price": "300.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-10",
        },
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["marketPriceUah"] is None
    assert created.json()["thumbnailUrl"] is None

    item = await db_session.get(CatalogItem, ctx.item_id)
    assert item is not None
    await add_snapshot(db_session, item, "77777.00", is_suspect=True)
    await add_snapshot(db_session, item, "450.00")

    listed = (await client.get("/api/v1/collection", headers=headers)).json()
    assert listed["items"][0]["marketPriceUah"] == "450.00"
    assert "thumbnailUrl" in listed["items"][0]
