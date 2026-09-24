"""`GET /catalog/lookup` — the purchase form's typeahead.

Same visibility as the catalog listing, one deliberate difference: the
storefront rule is off, so a country the collector picked out of the full
list finds what the shared catalog holds for it (docs/business-rules.md,
§13, and the note there about the purchase form).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.helpers import register_and_verify
from tests.seed import (
    make_catalog_item,
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
    refs = await seed_reference(db_session)
    email_a, token_a = await register_and_verify(client, mail_outbox)
    email_b, token_b = await register_and_verify(client, mail_outbox)
    id_a = await user_id_by_email(db_session, email_a)
    id_b = await user_id_by_email(db_session, email_b)

    shared_ua = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, denomination=refs.uah_2
    )
    shared_us = await make_catalog_item(
        db_session, country=refs.usa, title="Dolphin quarter", year=2004
    )
    own_a = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін мого сусіда", year=2019, created_by=id_a
    )
    own_b = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін чужий", year=2020, created_by=id_b
    )
    return SimpleNamespace(
        refs=refs,
        token_a=token_a,
        token_b=token_b,
        shared_ua=shared_ua,
        shared_us=shared_us,
        own_a=own_a,
        own_b=own_b,
    )


async def _lookup(client: AsyncClient, token: str, **params: object) -> list[int]:
    response = await client.get("/api/v1/catalog/lookup", params=params, headers=auth(token))
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()]


async def test_lookup_returns_shared_and_own_but_not_someone_elses(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    found = await _lookup(client, ctx.token_a, q="Дельфін")
    assert ctx.shared_ua.id in found
    assert ctx.own_a.id in found
    assert ctx.own_b.id not in found


async def test_lookup_narrows_to_one_country(client: AsyncClient, ctx: SimpleNamespace) -> None:
    """The form asks for the country first; the name search lives inside it."""
    found = await _lookup(client, ctx.token_a, q="Dolphin", countryId=ctx.refs.usa.id)
    assert found == [ctx.shared_us.id]

    assert await _lookup(client, ctx.token_a, q="Dolphin", countryId=ctx.refs.ukraine.id) == []


async def test_lookup_finds_a_coin_of_a_country_off_the_storefront(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Otherwise the collector enters a duplicate of a coin we already have.

    The country dropdown on the "Додати" form offers every issuer there has
    ever been, while the catalogue itself shows only confirmed, active ones —
    so the typeahead has to see further than the listing does (owner,
    2026-09-14).
    """
    await set_country_active(db_session, ctx.refs.usa, False)
    await set_country_catalog_confirmed(db_session, ctx.refs.usa, False)

    assert await _lookup(client, ctx.token_a, q="Dolphin", countryId=ctx.refs.usa.id) == [
        ctx.shared_us.id
    ]
    # The catalog listing itself is unchanged: the storefront rule still hides it.
    listing = await client.get(
        "/api/v1/catalog",
        params={"q": "Dolphin", "countryId": ctx.refs.usa.id},
        headers=auth(ctx.token_a),
    )
    assert listing.json()["items"] == []


async def test_lookup_skips_archived_items(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    archived = await make_catalog_item(
        db_session,
        country=ctx.refs.ukraine,
        title="Дельфін знятий",
        year=2015,
        is_archived=True,
        archive_reason="Withdrawn",
    )
    assert archived.id not in await _lookup(client, ctx.token_a, q="Дельфін")


async def test_lookup_matches_a_word_prefix(client: AsyncClient, ctx: SimpleNamespace) -> None:
    """Same search as the catalog box: "Дельф" already finds "Дельфін"."""
    assert ctx.shared_ua.id in await _lookup(client, ctx.token_a, q="Дельф")


async def test_lookup_requires_a_query(client: AsyncClient, ctx: SimpleNamespace) -> None:
    response = await client.get("/api/v1/catalog/lookup", headers=auth(ctx.token_a))
    assert response.status_code == 422
