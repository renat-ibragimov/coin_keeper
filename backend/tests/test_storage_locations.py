"""Storage locations: presets, get-or-create, isolation, defaults."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import StorageLocation
from app.models.enums import TranslationSource
from app.repositories.storage_locations import StorageLocationRepository
from app.services.storage_locations import apply_translation
from app.services.translation import TranslationResult
from tests.helpers import register_and_verify
from tests.seed import make_catalog_item, seed_reference, user_id_by_email


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
        item_id=item.id,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def _location_count(db_session: AsyncSession) -> int:
    return (await db_session.execute(select(func.count(StorageLocation.id)))).scalar_one()


def _names(response_json: list[dict[str, object]]) -> list[str]:
    return [row["name"] for row in response_json]  # type: ignore[misc]


async def test_lists_the_single_preset_before_anyone_adds_their_own(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    response = await client.get("/api/v1/collection/storage-locations", headers=auth(ctx.token_a))
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert "Вдома" in _names(rows)
    assert all(row["custom"] is False for row in rows)


async def test_new_purchase_creates_a_personal_location_visible_only_to_its_owner(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    before = await _location_count(db_session)
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "10.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
            "storageLocation": "У доньки",
        },
        headers=auth(ctx.token_a),
    )
    assert created.status_code == 201, created.text
    assert created.json()["storageLocation"] == "У доньки"

    after = await _location_count(db_session)
    assert after == before + 1

    # Visible to its own owner, and marked deletable...
    mine = await client.get("/api/v1/collection/storage-locations", headers=auth(ctx.token_a))
    mine_rows = mine.json()
    assert "У доньки" in _names(mine_rows)
    assert next(row for row in mine_rows if row["name"] == "У доньки")["custom"] is True
    # ...but not to another user, alongside the preset they still see.
    theirs = await client.get("/api/v1/collection/storage-locations", headers=auth(ctx.token_b))
    assert "У доньки" not in _names(theirs.json())
    assert len(theirs.json()) == 1


async def test_reusing_a_name_does_not_create_a_duplicate_entry(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    first = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "10.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
            "storageLocation": "Гараж",
        },
        headers=auth(ctx.token_a),
    )
    assert first.status_code == 201, first.text
    before = await _location_count(db_session)

    # Same text, different case and surrounding whitespace.
    second = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "20.00",
            "currency": "UAH",
            "purchaseDate": "2024-02-01",
            "storageLocation": "  гараж  ",
        },
        headers=auth(ctx.token_a),
    )
    assert second.status_code == 201, second.text
    assert second.json()["storageLocation"] == "Гараж"
    assert await _location_count(db_session) == before

    # A preset name matches the same way -- no second "Вдома" for this owner.
    third = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "5.00",
            "currency": "UAH",
            "purchaseDate": "2024-03-01",
            "storageLocation": "вдома",
        },
        headers=auth(ctx.token_a),
    )
    assert third.status_code == 201, third.text
    assert third.json()["storageLocation"] == "Вдома"
    assert await _location_count(db_session) == before


async def test_update_can_clear_the_storage_location(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    created = await client.post(
        "/api/v1/collection",
        json={
            "catalogItemId": ctx.item_id,
            "quantity": 1,
            "price": "10.00",
            "currency": "UAH",
            "purchaseDate": "2024-01-01",
            "storageLocation": "Вдома",
        },
        headers=auth(ctx.token_a),
    )
    item_id = created.json()["id"]

    cleared = await client.patch(
        f"/api/v1/collection/{item_id}",
        json={"storageLocation": None},
        headers=auth(ctx.token_a),
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["storageLocation"] is None


async def test_explicit_add_creates_a_deletable_personal_entry(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    before = await _location_count(db_session)
    added = await client.post(
        "/api/v1/collection/storage-locations",
        json={"name": "  Бабусина скринька  "},
        headers=auth(ctx.token_a),
    )
    assert added.status_code == 201, added.text
    assert added.json() == {"name": "Бабусина скринька", "custom": True}
    assert await _location_count(db_session) == before + 1

    # Adding the same name again reuses it rather than duplicating.
    again = await client.post(
        "/api/v1/collection/storage-locations",
        json={"name": "бабусина скринька"},
        headers=auth(ctx.token_a),
    )
    assert again.status_code == 201, again.text
    assert await _location_count(db_session) == before + 1


async def test_owner_can_delete_their_own_location(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    await client.post(
        "/api/v1/collection/storage-locations",
        json={"name": "Тимчасово"},
        headers=auth(ctx.token_a),
    )
    before = await _location_count(db_session)

    deleted = await client.request(
        "DELETE",
        "/api/v1/collection/storage-locations",
        params={"name": "Тимчасово"},
        headers=auth(ctx.token_a),
    )
    assert deleted.status_code == 204, deleted.text
    assert await _location_count(db_session) == before - 1

    remaining = await client.get("/api/v1/collection/storage-locations", headers=auth(ctx.token_a))
    assert "Тимчасово" not in _names(remaining.json())


async def test_cannot_delete_a_preset(client: AsyncClient, ctx: SimpleNamespace) -> None:
    response = await client.request(
        "DELETE",
        "/api/v1/collection/storage-locations",
        params={"name": "Вдома"},
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 403, response.text

    still_there = await client.get(
        "/api/v1/collection/storage-locations", headers=auth(ctx.token_a)
    )
    assert "Вдома" in _names(still_there.json())


async def test_cannot_delete_another_owners_location(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    await client.post(
        "/api/v1/collection/storage-locations",
        json={"name": "Приватне місце А"},
        headers=auth(ctx.token_a),
    )
    response = await client.request(
        "DELETE",
        "/api/v1/collection/storage-locations",
        params={"name": "Приватне місце А"},
        headers=auth(ctx.token_b),
    )
    assert response.status_code == 404, response.text


async def test_default_storage_location_setting_resolves_and_persists(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    fresh = await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))
    assert fresh.json()["settings"]["defaultStorageLocation"] is None

    updated = await client.patch(
        "/api/v1/bootstrap/settings",
        json={"defaultStorageLocation": "В дорозі"},
        headers=auth(ctx.token_a),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["defaultStorageLocation"] == "В дорозі"

    again = await client.get("/api/v1/bootstrap", headers=auth(ctx.token_a))
    assert again.json()["settings"]["defaultStorageLocation"] == "В дорозі"


def test_apply_translation_keeps_the_detected_language_slot_verbatim() -> None:
    location = StorageLocation(
        owner_id=1,
        name_original="вдома у батьків",
        name_uk="вдома у батьків",
        name_uk_source=TranslationSource.MANUAL,
        name_en="вдома у батьків",
        name_en_source=TranslationSource.MANUAL,
    )
    apply_translation(
        location,
        TranslationResult(language="uk", name_uk="ignored", name_en="at my parents'"),
    )
    assert location.name_uk == "вдома у батьків"  # untouched, still MANUAL
    assert location.name_uk_source == TranslationSource.MANUAL
    assert location.name_en == "at my parents'"
    assert location.name_en_source == TranslationSource.LLM


def test_apply_translation_fills_both_slots_for_a_third_language() -> None:
    location = StorageLocation(
        owner_id=1,
        name_original="w sejfie",
        name_uk="w sejfie",
        name_uk_source=TranslationSource.MANUAL,
        name_en="w sejfie",
        name_en_source=TranslationSource.MANUAL,
    )
    apply_translation(
        location,
        TranslationResult(language="other", name_uk="у сейфі", name_en="in a safe"),
    )
    assert location.name_uk == "у сейфі"
    assert location.name_uk_source == TranslationSource.LLM
    assert location.name_en == "in a safe"
    assert location.name_en_source == TranslationSource.LLM


async def test_add_commits_immediately_so_a_background_task_can_see_it(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """FastAPI runs BackgroundTasks as part of sending the response -- before
    this request's own end-of-request commit, not after (confirmed 2026-09-13
    by logging commit and background-task timestamps side by side against a
    live server: every location created this way came back untranslated,
    "vanished before translation ran" in the logs, because
    translate_in_background's separate session opened before this one had
    committed). add() must commit the row itself rather than leaving it for
    that later commit."""
    commit_spy = AsyncMock(wraps=db_session.commit)
    db_session.commit = commit_spy  # type: ignore[method-assign]

    repo = StorageLocationRepository(db_session, owner_id=ctx.id_a)
    await repo.add(
        StorageLocation(
            owner_id=ctx.id_a,
            name_original="Тестове місце",
            name_uk="Тестове місце",
            name_uk_source=TranslationSource.MANUAL,
            name_en="Тестове місце",
            name_en_source=TranslationSource.MANUAL,
        )
    )

    commit_spy.assert_awaited_once()
