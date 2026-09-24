"""Supporting expenses recorded together with the purchase they belong to.

`POST /collection` takes an `extraExpenses` list — delivery, a holder, a
grading fee — and writes them in the same transaction as the coin
(docs/business-rules.md, BR-4). Two properties are what these tests are
for: nothing is written at all if any rate in the request is missing, and what
comes out the other end is an ordinary manual expense, so deleting it later
leaves the coin exactly where it was.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

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
    make_catalog_item,
    seed_reference,
    user_id_by_email,
)

PURCHASE_DATE = "2024-05-20"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ctx(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> SimpleNamespace:
    refs = await seed_reference(db_session)
    email, token = await register_and_verify(client, mail_outbox)
    coin = await make_catalog_item(db_session, country=refs.ukraine, title="Дельфін", year=2018)
    return SimpleNamespace(
        refs=refs,
        token=token,
        user_id=await user_id_by_email(db_session, email),
        coin=coin,
    )


def purchase(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "quantity": 1,
        "price": "120.00",
        "currency": "UAH",
        "purchaseDate": PURCHASE_DATE,
        "seller": "Нумізматика UA",
    }
    body.update(overrides)
    return body


def new_coin(country_id: int) -> dict[str, Any]:
    return {
        "countryId": country_id,
        "titleOriginal": "Львівський оперний театр",
        "issueYear": 2021,
        "collectionGroup": "commemorative",
        "material": "Нейзильбер",
    }


async def _expenses_of(session: AsyncSession, catalog_item_id: int) -> list[Expense]:
    rows = await session.execute(
        select(Expense).where(Expense.catalog_item_id == catalog_item_id).order_by(Expense.id)
    )
    return list(rows.scalars().all())


async def test_delivery_is_written_with_the_purchase(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    response = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            extraExpenses=[{"category": "delivery", "amount": "60.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert response.status_code == 201, response.text

    expenses = await _expenses_of(db_session, ctx.coin.id)
    assert [e.category for e in expenses] == [
        ExpenseCategory.COIN_PURCHASE,
        ExpenseCategory.DELIVERY,
    ]
    delivery = expenses[1]
    assert str(delivery.amount) == "60.00"
    # Date and vendor come from the purchase — that is the whole point of
    # recording the two together rather than one after the other.
    assert delivery.expense_date.isoformat() == PURCHASE_DATE
    assert delivery.vendor == "Нумізматика UA"
    assert str(delivery.rate_uah) == "1.000000"
    # Linked to this exact purchase too, same as coin_purchase (2026-09-22) —
    # a repeat purchase of the same coin must not mix up whose delivery it was.
    purchase_row = (
        await db_session.execute(
            select(CollectionItem).where(CollectionItem.catalog_item_id == ctx.coin.id)
        )
    ).scalar_one()
    assert delivery.collection_item_id == purchase_row.id


async def test_extra_expense_keeps_its_own_currency(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """A coin bought in dollars is delivered by a courier paid in hryvnia."""
    await add_rate(db_session, "USD", "41.500000", date.fromisoformat(PURCHASE_DATE))
    response = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            currency="USD",
            price="10.00",
            extraExpenses=[{"category": "delivery", "amount": "80.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert response.status_code == 201, response.text

    expenses = await _expenses_of(db_session, ctx.coin.id)
    assert expenses[0].currency_code == "USD"
    assert str(expenses[0].rate_uah) == "41.500000"
    assert expenses[1].currency_code == "UAH"
    assert str(expenses[1].rate_uah) == "1.000000"


async def test_a_missing_rate_on_an_extra_leaves_nothing_behind(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The composite request's contract, from the side of the expense.

    A delivery in a currency the NBU has no rate for on that date rejects the
    whole thing — no coin, no instance, no purchase expense.
    """
    before = int((await db_session.execute(select(func.count(CatalogItem.id)))).scalar_one())
    response = await client.post(
        "/api/v1/collection",
        json=purchase(
            newCatalogItem=new_coin(ctx.refs.ukraine.id),
            extraExpenses=[{"category": "delivery", "amount": "9.00", "currency": "USD"}],
        ),
        headers=auth(ctx.token),
    )
    assert response.status_code == 422, response.text
    assert response.json()["type"].endswith("exchange-rate-missing")

    after = int((await db_session.execute(select(func.count(CatalogItem.id)))).scalar_one())
    assert after == before
    instances = (await db_session.execute(select(func.count(CollectionItem.id)))).scalar_one()
    assert int(instances) == 0
    expenses = (await db_session.execute(select(func.count(Expense.id)))).scalar_one()
    assert int(expenses) == 0


async def test_extras_ride_along_with_a_new_coin(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    response = await client.post(
        "/api/v1/collection",
        json=purchase(
            newCatalogItem=new_coin(ctx.refs.ukraine.id),
            extraExpenses=[
                {"category": "delivery", "amount": "60.00", "currency": "UAH"},
                {"category": "holder", "amount": "25.00", "currency": "UAH"},
            ],
        ),
        headers=auth(ctx.token),
    )
    assert response.status_code == 201, response.text
    catalog_item_id = response.json()["catalogItemId"]

    expenses = await _expenses_of(db_session, catalog_item_id)
    assert [e.category for e in expenses] == [
        ExpenseCategory.COIN_PURCHASE,
        ExpenseCategory.DELIVERY,
        ExpenseCategory.HOLDER,
    ]


async def test_deleting_an_extra_expense_leaves_the_coin(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The other direction of the link, and the reason it is not a strong one.

    A delivery deleted from the money journal is just an expense going away:
    the coin, the instance and the purchase expense all stay (owner's call,
    2026-09-14).
    """
    created = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            extraExpenses=[{"category": "delivery", "amount": "60.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert created.status_code == 201, created.text
    instance_id = created.json()["id"]

    expenses = await _expenses_of(db_session, ctx.coin.id)
    delivery_id = expenses[1].id
    deleted = await client.delete(f"/api/v1/expenses/{delivery_id}", headers=auth(ctx.token))
    assert deleted.status_code == 204, deleted.text

    still_there = await client.get(f"/api/v1/collection/{instance_id}", headers=auth(ctx.token))
    assert still_there.status_code == 200
    db_session.expire_all()
    remaining = await _expenses_of(db_session, ctx.coin.id)
    assert [e.category for e in remaining] == [ExpenseCategory.COIN_PURCHASE]


async def test_repeat_purchase_keeps_its_own_delivery(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The whole reason `collection_item_id` exists on a supporting expense
    (2026-09-22): the same coin bought twice, each time with its own
    delivery, must not mix the two up. The item-level total still sums both,
    but each purchase in `collection-items` only ever shows its own.
    """
    first = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            extraExpenses=[{"category": "delivery", "amount": "60.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    second = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            purchaseDate="2024-06-01",
            extraExpenses=[{"category": "holder", "amount": "25.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_id, second_id = first.json()["id"], second.json()["id"]

    expenses = await _expenses_of(db_session, ctx.coin.id)
    by_category = {e.category: e for e in expenses if e.category != ExpenseCategory.COIN_PURCHASE}
    assert by_category[ExpenseCategory.DELIVERY].collection_item_id == first_id
    assert by_category[ExpenseCategory.HOLDER].collection_item_id == second_id

    card = (await client.get(f"/api/v1/catalog/{ctx.coin.id}", headers=auth(ctx.token))).json()
    assert card["supportingExpensesUah"] == "85.00"

    instances = {
        row["id"]: row["supportingExpensesUah"]
        for row in (
            await client.get(
                f"/api/v1/catalog/{ctx.coin.id}/collection-items", headers=auth(ctx.token)
            )
        ).json()
    }
    assert instances[first_id] == "60.00"
    assert instances[second_id] == "25.00"


async def test_deleting_the_instance_detaches_but_keeps_the_delivery(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Unlike `coin_purchase`, a supporting expense is never deleted by the
    service — `collection_item_id`'s `ON DELETE SET NULL` detaches it on its
    own, and the money stays in the journal (docs/business-rules.md,
    BR-4 and BR-10)."""
    created = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            extraExpenses=[{"category": "delivery", "amount": "60.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert created.status_code == 201, created.text
    instance_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/collection/{instance_id}", headers=auth(ctx.token))
    assert deleted.status_code == 204, deleted.text

    db_session.expire_all()
    remaining = await _expenses_of(db_session, ctx.coin.id)
    assert [e.category for e in remaining] == [ExpenseCategory.DELIVERY]
    assert remaining[0].collection_item_id is None
    assert remaining[0].catalog_item_id == ctx.coin.id


async def test_coin_purchase_cannot_be_listed_as_an_extra(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    """The purchase writes its own coin_purchase row; a second one would double
    the coin spending on every chart (docs/business-rules.md, BR-6)."""
    response = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            extraExpenses=[{"category": "coin_purchase", "amount": "60.00", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert response.status_code == 422, response.text


async def test_an_extra_of_zero_is_rejected(client: AsyncClient, ctx: SimpleNamespace) -> None:
    """Unlike a coin, which can honestly have cost nothing."""
    response = await client.post(
        "/api/v1/collection",
        json=purchase(
            catalogItemId=ctx.coin.id,
            extraExpenses=[{"category": "delivery", "amount": "0", "currency": "UAH"}],
        ),
        headers=auth(ctx.token),
    )
    assert response.status_code == 422, response.text


async def test_no_extras_is_the_ordinary_purchase(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    response = await client.post(
        "/api/v1/collection",
        json=purchase(catalogItemId=ctx.coin.id),
        headers=auth(ctx.token),
    )
    assert response.status_code == 201, response.text
    expenses = await _expenses_of(db_session, ctx.coin.id)
    assert [e.category for e in expenses] == [ExpenseCategory.COIN_PURCHASE]
