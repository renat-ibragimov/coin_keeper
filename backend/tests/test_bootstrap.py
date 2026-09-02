"""GET /bootstrap: dashboard figures, finance, rates, isolation."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.helpers import register_and_verify
from tests.seed import (
    add_collection_item,
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
    return SimpleNamespace(
        refs=refs,
        email_a=email_a,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def test_empty_dashboard_for_new_user(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await make_catalog_item(db_session, country=ctx.refs.ukraine, title="Дельфін", year=2018)

    body = (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))).json()
    dashboard = body["dashboard"]
    # The shared catalog is there, but the user's collection is empty.
    assert dashboard["catalogItems"] == 1
    assert dashboard["collectionItems"] == 0
    assert dashboard["completedItems"] == 0
    assert dashboard["coinSpendUah"] == "0.00"
    assert dashboard["marketValueUah"] == "0.00"
    assert dashboard["isEmpty"] is True

    assert body["user"]["email"] == ctx.email_a
    assert body["settings"]["locale"] == "uk"
    assert body["settings"]["displayCurrency"] == "UAH"

    finance = body["finance"]
    assert finance["coinSpendUah"] == "0.00"
    assert finance["coinSpendUsdAtPurchase"] == "0.00"
    assert finance["purchasesWithoutHistoricalUsdRate"] == 0

    rates = {row["code"]: row for row in body["exchangeRates"]}
    assert set(rates) == {"USD", "EUR"}
    assert rates["USD"]["rate"] is None


async def test_dashboard_figures(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    dolphin = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=refs.fauna
    )
    owl = await make_catalog_item(
        db_session, country=refs.ukraine, title="Сова", year=2017, series=refs.fauna
    )
    kyiv = await make_catalog_item(
        db_session, country=refs.ukraine, title="Київ", year=2020, series=refs.cities
    )
    await make_catalog_item(db_session, country=refs.usa, title="Lincoln cent", year=2009)
    archived = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Архівна",
        year=2015,
        is_archived=True,
        archive_reason="duplicate",
    )
    # B's personal item must change nothing in A's numbers.
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Особиста Б", year=2014, created_by=ctx.id_b
    )

    # A holds: two dolphins (one row, quantity 2), one kyiv, one archived coin.
    await add_collection_item(db_session, owner_id=ctx.id_a, item=dolphin, quantity=2, price="100")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=kyiv, price="50")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=archived, price="30")

    await add_snapshot(db_session, dolphin, "150.00")
    await add_snapshot(db_session, owl, "200.00")
    await add_snapshot(db_session, archived, "500.00")
    # cent has no price: it is the unpriced missing one.
    # A suspect price on owl must not shadow the good one.
    await add_snapshot(db_session, owl, "99999.00", is_suspect=True)

    body = (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))).json()
    dashboard = body["dashboard"]

    # Visible active: dolphin, owl, kyiv, cent.
    assert dashboard["catalogItems"] == 4
    assert dashboard["countries"] == 2
    # 2 dolphins + 1 kyiv + 1 archived coin.
    assert dashboard["collectionItems"] == 4
    # Completed: dolphin and kyiv (archived does not count).
    assert dashboard["completedItems"] == 2
    assert dashboard["missingItems"] == 2
    assert dashboard["completionPercent"] == 50.0
    # Spend: 2x100 + 50 + 30.
    assert dashboard["coinSpendUah"] == "280.00"
    assert dashboard["totalSpendUah"] == "280.00"
    # Value: 2x150 (dolphin) + 0 (kyiv unpriced) + 500 (archived instance).
    assert dashboard["marketValueUah"] == "800.00"
    # Missing budget: owl 200; cent unpriced adds 0.
    assert dashboard["missingBudgetUah"] == "200.00"
    assert dashboard["unpricedMissingItems"] == 1
    assert dashboard["isEmpty"] is False

    countries = {row["name"]: row for row in dashboard["countryBreakdown"]}
    assert countries["Україна"]["count"] == 3
    assert countries["Україна"]["owned"] == 2
    assert countries["США"]["count"] == 1
    assert countries["США"]["owned"] == 0

    series = {row["name"]: row for row in dashboard["seriesBreakdown"]}
    assert series["Флора і фауна"]["count"] == 2
    assert series["Флора і фауна"]["owned"] == 1
    assert series["Флора і фауна"]["country"] == "Україна"
    assert series["Міста України"]["owned"] == 1


async def test_finance_at_purchase_rates(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(db_session, country=refs.ukraine, title="Дельфін", year=2018)
    await add_rate(db_session, "USD", "25.00", date(2024, 1, 1))
    await add_rate(db_session, "USD", "40.00", date(2026, 1, 1))
    await add_rate(db_session, "EUR", "30.00", date(2025, 6, 1))

    # Two purchases: 100 UAH when USD was 25, and 200 UAH when USD was 40.
    await add_collection_item(
        db_session,
        owner_id=ctx.id_a,
        item=item,
        price="100",
        acquisition_date=date(2024, 6, 1),
    )
    await add_collection_item(
        db_session,
        owner_id=ctx.id_a,
        item=item,
        price="200",
        acquisition_date=date(2026, 2, 1),
    )

    finance = (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))).json()["finance"]
    assert finance["coinSpendUah"] == "300.00"
    # 100/25 + 200/40 = 4 + 5 = 9 USD at purchase.
    assert finance["coinSpendUsdAtPurchase"] == "9.00"
    # The first purchase predates any EUR rate: only the second converts.
    assert finance["coinSpendEurAtPurchase"] == "6.67"
    assert finance["purchasesWithoutHistoricalUsdRate"] == 0
    assert finance["purchasesWithoutHistoricalEurRate"] == 1

    rates = {
        row["code"]: row
        for row in (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))).json()[
            "exchangeRates"
        ]
    }
    assert rates["USD"]["rate"] == "40"
    assert rates["USD"]["effectiveDate"] == "2026-01-01"
    assert rates["EUR"]["rate"] == "30"


async def test_bootstrap_isolation(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(db_session, country=refs.ukraine, title="Дельфін", year=2018)
    await add_collection_item(db_session, owner_id=ctx.id_a, item=item, price="100")
    # A's own snapshot must not leak into B's valuation.
    await add_snapshot(db_session, item, "1000.00", created_by=ctx.id_a, source="Manual")

    body_b = (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_b))).json()
    assert body_b["dashboard"]["collectionItems"] == 0
    assert body_b["dashboard"]["coinSpendUah"] == "0.00"
    assert body_b["dashboard"]["marketValueUah"] == "0.00"
    # B still misses the item, and for B it has no visible price at all.
    assert body_b["dashboard"]["missingBudgetUah"] == "0.00"
    assert body_b["dashboard"]["unpricedMissingItems"] == 1
    assert body_b["dashboard"]["isEmpty"] is True

    body_a = (await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))).json()
    assert body_a["dashboard"]["marketValueUah"] == "1000.00"
