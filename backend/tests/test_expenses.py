"""Expenses: CRUD, the coin_purchase guard, rate handling, summary."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.helpers import register_and_verify
from tests.seed import (
    add_rate,
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
    item = await make_catalog_item(db_session, country=refs.ukraine, title="Дельфін", year=2018)
    return SimpleNamespace(
        refs=refs,
        item_id=item.id,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def _add_purchase(client: AsyncClient, token: str, item_id: int, price: str) -> int:
    response = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": item_id,
            "quantity": 1,
            "price": price,
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_expense_crud(client: AsyncClient, ctx: SimpleNamespace) -> None:
    headers = auth(ctx.token_a)
    created = await client.post(
        "/api/v1/expenses",
        json={
            "category": "album",
            "amount": "350.00",
            "currency": "UAH",
            "expenseDate": "2024-02-01",
            "vendor": "Rozetka",
            "description": "Album for 2-hryvnia coins",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["amountUah"] == "350.00"
    assert body["rateUah"] == "1"
    expense_id = body["id"]

    listing = await client.get("/api/v1/expenses", headers=headers)
    assert listing.json()["total"] == 1

    updated = await client.patch(
        f"/api/v1/expenses/{expense_id}", json={"amount": "400.00"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["amountUah"] == "400.00"

    deleted = await client.delete(f"/api/v1/expenses/{expense_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/expenses", headers=headers)).json()["total"] == 0


async def test_expense_in_foreign_currency(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await add_rate(db_session, "EUR", "45.00", date(2024, 1, 10))
    headers = auth(ctx.token_a)

    ok = await client.post(
        "/api/v1/expenses",
        json={
            "category": "delivery",
            "amount": "10.00",
            "currency": "EUR",
            "expenseDate": "2024-01-15",
        },
        headers=headers,
    )
    assert ok.status_code == 201
    assert ok.json()["amountUah"] == "450.00"

    no_rate = await client.post(
        "/api/v1/expenses",
        json={
            "category": "delivery",
            "amount": "10.00",
            "currency": "EUR",
            "expenseDate": "2024-01-05",
        },
        headers=headers,
    )
    assert no_rate.status_code == 422
    assert "exchange-rate-missing" in no_rate.json()["type"]


async def test_coin_purchase_guard(client: AsyncClient, ctx: SimpleNamespace) -> None:
    headers = auth(ctx.token_a)

    direct_create = await client.post(
        "/api/v1/expenses",
        json={
            "category": "coin_purchase",
            "amount": "100.00",
            "currency": "UAH",
            "expenseDate": "2024-01-01",
        },
        headers=headers,
    )
    assert direct_create.status_code == 409

    await _add_purchase(client, ctx.token_a, ctx.item_id, "120.00")
    listing = await client.get("/api/v1/expenses?category=coin_purchase", headers=headers)
    assert listing.json()["total"] == 1
    purchase_expense_id = listing.json()["items"][0]["id"]

    patch = await client.patch(
        f"/api/v1/expenses/{purchase_expense_id}", json={"amount": "1.00"}, headers=headers
    )
    assert patch.status_code == 409

    delete = await client.delete(f"/api/v1/expenses/{purchase_expense_id}", headers=headers)
    assert delete.status_code == 409

    switch_to_purchase = await client.post(
        "/api/v1/expenses",
        json={
            "category": "album",
            "amount": "10.00",
            "currency": "UAH",
            "expenseDate": "2024-01-01",
        },
        headers=headers,
    )
    patched = await client.patch(
        f"/api/v1/expenses/{switch_to_purchase.json()['id']}",
        json={"category": "coin_purchase"},
        headers=headers,
    )
    assert patched.status_code == 409


async def test_filters_and_isolation(client: AsyncClient, ctx: SimpleNamespace) -> None:
    headers_a = auth(ctx.token_a)
    for category, amount, expense_date in (
        ("album", "100.00", "2024-01-10"),
        ("delivery", "50.00", "2024-02-10"),
        ("delivery", "70.00", "2024-03-10"),
    ):
        response = await client.post(
            "/api/v1/expenses",
            json={
                "category": category,
                "amount": amount,
                "currency": "UAH",
                "expenseDate": expense_date,
            },
            headers=headers_a,
        )
        assert response.status_code == 201

    by_category = await client.get("/api/v1/expenses?category=delivery", headers=headers_a)
    assert by_category.json()["total"] == 2

    by_dates = await client.get(
        "/api/v1/expenses?dateFrom=2024-02-01&dateTo=2024-02-28", headers=headers_a
    )
    assert by_dates.json()["total"] == 1
    assert by_dates.json()["items"][0]["amount"] == "50.00"

    listing_b = await client.get("/api/v1/expenses", headers=auth(ctx.token_b))
    assert listing_b.json()["total"] == 0

    expense_id = by_dates.json()["items"][0]["id"]
    foreign_patch = await client.patch(
        f"/api/v1/expenses/{expense_id}", json={"amount": "1.00"}, headers=auth(ctx.token_b)
    )
    assert foreign_patch.status_code == 404


async def test_summary(client: AsyncClient, ctx: SimpleNamespace) -> None:
    headers = auth(ctx.token_a)
    await _add_purchase(client, ctx.token_a, ctx.item_id, "300.00")
    for category, amount in (("album", "100.00"), ("delivery", "44.50")):
        await client.post(
            "/api/v1/expenses",
            json={
                "category": category,
                "amount": amount,
                "currency": "UAH",
                "expenseDate": "2024-01-01",
            },
            headers=headers,
        )

    summary = (await client.get("/api/v1/expenses/summary", headers=headers)).json()
    assert summary["coinSpendUah"] == "300.00"
    assert summary["relatedSpendUah"] == "144.50"
    assert summary["totalUah"] == "444.50"
    by_category = {row["category"]: row for row in summary["categories"]}
    assert by_category["coin_purchase"]["totalUah"] == "300.00"
    assert by_category["album"]["count"] == 1

    # B's summary is empty.
    summary_b = (await client.get("/api/v1/expenses/summary", headers=auth(ctx.token_b))).json()
    assert summary_b["totalUah"] == "0.00"
    assert summary_b["categories"] == []
