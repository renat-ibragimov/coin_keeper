"""Buying a coin the catalog does not have yet.

`POST /collection` with `newCatalogItem` creates the personal catalog item,
the instance and the coin_purchase expense in one transaction
(docs/04-business-rules.md, rule 4). What the tests here are actually about
is that "one transaction" — a purchase rejected for a missing rate must not
leave a coin nobody bought behind.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import CatalogItem, CollectionItem, Expense, Material
from app.models.enums import ExpenseCategory, TranslationSource
from tests.helpers import register_and_verify
from tests.seed import (
    add_rate,
    country_by_code,
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
    return SimpleNamespace(
        refs=refs,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


def purchase(coin: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "newCatalogItem": coin,
        "quantity": 1,
        "price": "120.00",
        "currency": "UAH",
        "purchaseDate": "2024-05-20",
    }
    body.update(overrides)
    return body


def coin_payload(country_id: int, **overrides: Any) -> dict[str, Any]:
    """The shortest coin the form can send: country, name, year, type, material."""
    body: dict[str, Any] = {
        "countryId": country_id,
        "titleOriginal": "Львівський оперний театр",
        "issueYear": 2021,
        "collectionGroup": "commemorative",
        "material": "Нейзильбер",
    }
    body.update(overrides)
    return body


async def _catalog_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(CatalogItem.id)))).scalar_one())


async def test_new_coin_creates_item_instance_and_expense(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.ukraine.id), quantity=2, price="150.50"),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Львівський оперний театр"
    assert body["quantity"] == 2

    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.id == body["catalogItemId"]))
    ).scalar_one()
    # A personal item, never a shared one: the shared catalog stays read-only
    # for a regular user whichever door the record comes through (CLAUDE.md).
    assert item.created_by == ctx.id_a
    assert item.title_original == "Львівський оперний театр"
    assert item.issue_year == 2021
    assert item.material == "Нейзильбер"
    # Both language slots start out holding what the collector typed, exactly
    # as a new storage location does; the background job replaces the one that
    # is a translation rather than a copy.
    assert item.title_uk == "Львівський оперний театр"
    assert item.title_en == "Львівський оперний театр"
    assert item.title_uk_source == TranslationSource.MANUAL
    assert item.title_en_source == TranslationSource.MANUAL

    instances = (
        (
            await db_session.execute(
                select(CollectionItem).where(CollectionItem.catalog_item_id == item.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(instances) == 1
    expense = (
        await db_session.execute(
            select(Expense).where(Expense.collection_item_id == instances[0].id)
        )
    ).scalar_one()
    assert expense.category == ExpenseCategory.COIN_PURCHASE
    assert str(expense.amount) == "301.00"
    assert expense.catalog_item_id == item.id


async def test_missing_rate_leaves_no_catalog_item_behind(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The whole reason the request is composite (docs/03-api-contract.md)."""
    before = await _catalog_count(db_session)
    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.ukraine.id), currency="USD"),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("exchange-rate-missing")
    assert await _catalog_count(db_session) == before


async def test_rate_is_resolved_before_anything_is_written(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await add_rate(db_session, "USD", "39.50", date(2024, 5, 1))
    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.ukraine.id), currency="USD", price="10.00"),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    assert response.json()["rateUah"] == "39.5"


async def test_unknown_currency_leaves_no_catalog_item_behind(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    before = await _catalog_count(db_session)
    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.ukraine.id), currency="XXX"),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("unknown-currency")
    assert await _catalog_count(db_session) == before


@pytest.mark.parametrize(
    ("changes", "what"),
    [
        ({}, "neither"),
        ({"catalogItemId": 1}, "both"),
    ],
)
async def test_exactly_one_coin_reference_is_required(
    client: AsyncClient, ctx: SimpleNamespace, changes: dict[str, Any], what: str
) -> None:
    body = purchase(coin_payload(ctx.refs.ukraine.id))
    if what == "neither":
        body.pop("newCatalogItem")
    body.update(changes)
    response = await client.post("/api/v1/collection", json=body, headers=auth(ctx.token_a))
    assert response.status_code == 422, what


async def test_unknown_country_is_rejected(client: AsyncClient, ctx: SimpleNamespace) -> None:
    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(10_000_000)),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-reference")


async def test_series_of_another_country_is_rejected(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    before = await _catalog_count(db_session)
    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.usa.id, seriesId=ctx.refs.fauna.id)),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-reference")
    assert await _catalog_count(db_session) == before


async def test_material_is_required_in_one_of_its_two_shapes(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    coin = coin_payload(ctx.refs.ukraine.id)
    coin.pop("material")
    response = await client.post(
        "/api/v1/collection", json=purchase(coin), headers=auth(ctx.token_a)
    )
    assert response.status_code == 422

    material = (await db_session.execute(select(Material).limit(1))).scalar_one()
    coin["compositionId"] = material.id
    response = await client.post(
        "/api/v1/collection", json=purchase(coin), headers=auth(ctx.token_a)
    )
    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Львівський оперний театр"


async def test_new_coin_is_invisible_to_other_users(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    created = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.ukraine.id)),
        headers=auth(ctx.token_a),
    )
    item_id = created.json()["catalogItemId"]

    mine = await client.get(f"/api/v1/catalog/{item_id}", headers=auth(ctx.token_a))
    assert mine.status_code == 200
    assert mine.json()["isOwn"] is True

    theirs = await client.get(f"/api/v1/catalog/{item_id}", headers=auth(ctx.token_b))
    assert theirs.status_code == 404


async def test_the_whole_transaction_commits_before_the_background_task_runs(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """FastAPI runs BackgroundTasks before this request's own end-of-request
    commit (the lesson storage locations paid for on 2026-09-13), and the
    translation task opens a session of its own — an uncommitted coin is a
    coin it cannot see. One commit, all three rows."""
    commit_spy = AsyncMock(wraps=db_session.commit)
    db_session.commit = commit_spy  # type: ignore[method-assign]

    response = await client.post(
        "/api/v1/collection",
        json=purchase(coin_payload(ctx.refs.ukraine.id)),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    commit_spy.assert_awaited()


async def test_a_purchase_of_a_known_coin_still_takes_the_plain_path(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The composite branch must not change what an ordinary purchase does."""
    item = await make_catalog_item(db_session, country=ctx.refs.ukraine, title="Дельфін", year=2018)
    before = await _catalog_count(db_session)
    response = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": item.id,
            "quantity": 1,
            "price": "120.00",
            "currency": "UAH",
            "purchaseDate": "2024-05-20",
        },
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    assert response.json()["catalogItemId"] == item.id
    assert await _catalog_count(db_session) == before


async def test_a_coin_of_a_country_with_no_dictionaries_keeps_its_own_words(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """An Austrian 5 euro: the denominations table has nothing for that
    country and neither does the series list, so both are typed in
    (docs/04-business-rules.md, §14, owner 2026-09-14)."""
    austria = await country_by_code(db_session, "AT")
    coin = coin_payload(
        austria.id,
        titleOriginal="5 Євро",
        denominationText="5 євро",
        seriesText="Австрійські казки",
    )
    response = await client.post(
        "/api/v1/collection", json=purchase(coin), headers=auth(ctx.token_a)
    )
    assert response.status_code == 201, response.text

    item_id = response.json()["catalogItemId"]
    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.id == item_id))
    ).scalar_one()
    assert item.denomination_id is None
    assert item.denomination_text == "5 євро"
    assert item.series_id is None
    assert item.series_text == "Австрійські казки"

    # Both show where the dictionary values would have: the card falls back
    # to the text, and so does the collection row.
    card = (await client.get(f"/api/v1/catalog/{item_id}", headers=auth(ctx.token_a))).json()
    assert card["denomination"] is None
    assert card["denominationText"] == "5 євро"
    assert card["seriesName"] == "Австрійські казки"

    position = next(
        row
        for row in (await client.get("/api/v1/collection", headers=auth(ctx.token_a))).json()[
            "items"
        ]
        if row["catalogItemId"] == item_id
    )
    assert position["denomination"] == "5 євро"
    assert position["seriesName"] == "Австрійські казки"
