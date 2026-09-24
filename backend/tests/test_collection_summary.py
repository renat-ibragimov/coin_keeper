"""GET /collection/summary: the "Мої монети" KPI tiles, scoped to the same
filters GET /collection accepts (docs/ui.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import Expense
from app.models.enums import ExpenseCategory
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


async def test_summary_matches_the_unfiltered_dashboard_snapshot(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(db_session, country=refs.ukraine, title="Дельфін", year=2018)
    await add_collection_item(db_session, owner_id=ctx.id_a, item=item, price="150", quantity=2)
    await add_snapshot(db_session, item, "90")

    dashboard = (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))).json()[
        "dashboard"
    ]
    summary = (await client.get("/api/v1/collection/summary", headers=auth(ctx.token_a))).json()

    assert summary["collectionItems"] == dashboard["collectionItems"] == 2
    assert summary["coinSpendUah"] == dashboard["coinSpendUah"] == "300.00"
    assert summary["marketValueUah"] == dashboard["marketValueUah"] == "180.00"
    assert Decimal(summary["totalSpendUah"]) == Decimal(summary["coinSpendUah"]) + Decimal(
        summary["relatedSpendUah"]
    )


async def test_related_expenses_are_included_and_filtered(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    ukraine_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018
    )
    instance = await add_collection_item(
        db_session, owner_id=ctx.id_a, item=ukraine_item, price="150"
    )
    db_session.add(
        Expense(
            owner_id=ctx.id_a,
            category=ExpenseCategory.DELIVERY,
            amount=Decimal("25.00"),
            currency_code="UAH",
            rate_uah=Decimal(1),
            expense_date=date(2024, 1, 15),
            catalog_item_id=ukraine_item.id,
            collection_item_id=instance.id,
        )
    )
    await db_session.commit()

    summary = (await client.get("/api/v1/collection/summary", headers=auth(ctx.token_a))).json()
    assert summary["coinSpendUah"] == "150.00"
    assert summary["relatedSpendUah"] == "25.00"
    assert summary["totalSpendUah"] == "175.00"


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
            f"/api/v1/collection/summary?countryId={refs.ukraine.id}", headers=auth(ctx.token_a)
        )
    ).json()
    assert ukraine_only["collectionItems"] == 1
    assert ukraine_only["coinSpendUah"] == "100.00"

    all_countries = (
        await client.get("/api/v1/collection/summary", headers=auth(ctx.token_a))
    ).json()
    assert all_countries["collectionItems"] == 2
    assert all_countries["coinSpendUah"] == "300.00"
