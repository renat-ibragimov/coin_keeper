"""Catalog writes: personal CRUD, admin rights, archiving, deletion rules."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import (
    AuditLog,
    CatalogItem,
    CollectionItem,
    Expense,
    MarketPriceSnapshot,
)
from app.models.enums import TranslationSource
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
    """User A is a regular user, user B is an admin."""
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


def _payload(ctx: SimpleNamespace, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "countryId": ctx.refs.ukraine.id,
        "collectionGroup": "commemorative",
        "titleOriginal": "Нова монета",
        "issueYear": 2024,
    }
    base.update(extra)
    return base


async def test_create_personal_item(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    response = await client.post(
        "/api/v1/catalog",
        json=_payload(ctx, seriesId=ctx.refs.fauna.id, denominationId=ctx.refs.uah_2.id),
        headers=auth(ctx.token_a),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["isOwn"] is True
    assert body["title"] == "Нова монета"

    created_by = (
        await db_session.execute(select(CatalogItem.created_by).where(CatalogItem.id == body["id"]))
    ).scalar_one()
    assert created_by == ctx.id_a


async def test_create_shared_requires_admin(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    denied = await client.post(
        "/api/v1/catalog", json=_payload(ctx, shared=True), headers=auth(ctx.token_a)
    )
    assert denied.status_code == 403

    allowed = await client.post(
        "/api/v1/catalog", json=_payload(ctx, shared=True), headers=auth(ctx.token_b)
    )
    assert allowed.status_code == 201
    body = allowed.json()
    assert body["isOwn"] is False
    created_by = (
        await db_session.execute(select(CatalogItem.created_by).where(CatalogItem.id == body["id"]))
    ).scalar_one()
    assert created_by is None


async def test_create_with_bad_references(client: AsyncClient, ctx: SimpleNamespace) -> None:
    bad_country = await client.post(
        "/api/v1/catalog", json=_payload(ctx, countryId=999999), headers=auth(ctx.token_a)
    )
    assert bad_country.status_code == 422

    # The series exists but belongs to Ukraine, the item claims the USA.
    mismatch = await client.post(
        "/api/v1/catalog",
        json=_payload(ctx, countryId=ctx.refs.usa.id, seriesId=ctx.refs.fauna.id),
        headers=auth(ctx.token_a),
    )
    assert mismatch.status_code == 422


async def test_patch_rights_matrix(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    shared = await make_catalog_item(db_session, country=refs.ukraine, title="Спільна", year=2020)
    own_a = await make_catalog_item(
        db_session, country=refs.ukraine, title="Своя А", year=2021, created_by=ctx.id_a
    )
    shared_id, own_a_id = shared.id, own_a.id
    changes = {"material": "срібло"}

    own_ok = await client.patch(
        f"/api/v1/catalog/{own_a_id}", json=changes, headers=auth(ctx.token_a)
    )
    assert own_ok.status_code == 200
    assert own_ok.json()["material"] == "срібло"

    shared_denied = await client.patch(
        f"/api/v1/catalog/{shared_id}", json=changes, headers=auth(ctx.token_a)
    )
    assert shared_denied.status_code == 403

    shared_admin = await client.patch(
        f"/api/v1/catalog/{shared_id}", json=changes, headers=auth(ctx.token_b)
    )
    assert shared_admin.status_code == 200

    foreign = await client.patch(
        f"/api/v1/catalog/{own_a_id}", json=changes, headers=auth(ctx.token_b)
    )
    assert foreign.status_code == 404


async def test_admin_title_edit_sets_manual_source_and_validates_nonempty(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """PATCH-ing a shared record's names is an admin operation, and whatever
    it writes is provenance 'manual', never the pipeline's 'official' or
    'llm' (docs/02-data-model.md; docs/05-integrations.md, part C).
    """
    refs = ctx.refs
    shared = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Стара назва",
        year=2020,
        title_uk="Стара назва",
        title_uk_source=TranslationSource.LLM,
        title_en="Old title",
        title_en_source=TranslationSource.LLM,
    )

    edited = await client.patch(
        f"/api/v1/catalog/{shared.id}",
        json={
            "titleOriginal": "Стара назва",
            "titleUk": "Нова офіційна назва",
            "titleEn": "New official title",
        },
        headers=auth(ctx.token_b),
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["titleUk"] == "Нова офіційна назва"
    assert body["titleUkSource"] == "manual"
    assert body["titleEnSource"] == "manual"

    stored = await db_session.get(CatalogItem, shared.id)
    assert stored is not None
    assert stored.title_uk_source is TranslationSource.MANUAL
    assert stored.title_en_source is TranslationSource.MANUAL

    empty = await client.patch(
        f"/api/v1/catalog/{shared.id}", json={"titleUk": ""}, headers=auth(ctx.token_b)
    )
    assert empty.status_code == 422

    denied = await client.patch(
        f"/api/v1/catalog/{shared.id}",
        json={"titleUk": "Спроба користувача"},
        headers=auth(ctx.token_a),
    )
    assert denied.status_code == 403


async def test_delete_personal_cascades_instances_and_expenses(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Своя", year=2021, created_by=ctx.id_a
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=item, price="120")
    item_id = item.id

    response = await client.delete(f"/api/v1/catalog/{item_id}", headers=auth(ctx.token_a))
    assert response.status_code == 204

    remaining_items = (
        await db_session.execute(
            select(func.count(CatalogItem.id)).where(CatalogItem.id == item_id)
        )
    ).scalar_one()
    remaining_instances = (
        await db_session.execute(
            select(func.count(CollectionItem.id)).where(CollectionItem.catalog_item_id == item_id)
        )
    ).scalar_one()
    remaining_expenses = (
        await db_session.execute(select(func.count(Expense.id)).where(Expense.owner_id == ctx.id_a))
    ).scalar_one()
    assert (remaining_items, remaining_instances, remaining_expenses) == (0, 0, 0)

    audit = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "catalog_item.delete")))
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].entity_id == str(item_id)


async def test_delete_shared_rules(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    active = await make_catalog_item(db_session, country=refs.ukraine, title="Активна", year=2020)
    referenced = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="З монетами",
        year=2019,
        is_archived=True,
        archive_reason="duplicate",
    )
    clean = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Порожня",
        year=2018,
        is_archived=True,
        archive_reason="typo",
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=referenced, price="10")
    await add_snapshot(db_session, clean, "5.00")
    active_id, referenced_id, clean_id = active.id, referenced.id, clean.id

    by_user = await client.delete(f"/api/v1/catalog/{active_id}", headers=auth(ctx.token_a))
    assert by_user.status_code == 403

    not_archived = await client.delete(f"/api/v1/catalog/{active_id}", headers=auth(ctx.token_b))
    assert not_archived.status_code == 409

    with_refs = await client.delete(f"/api/v1/catalog/{referenced_id}", headers=auth(ctx.token_b))
    assert with_refs.status_code == 409

    ok = await client.delete(f"/api/v1/catalog/{clean_id}", headers=auth(ctx.token_b))
    assert ok.status_code == 204
    snapshots = (
        await db_session.execute(
            select(func.count(MarketPriceSnapshot.id)).where(
                MarketPriceSnapshot.catalog_item_id == clean_id
            )
        )
    ).scalar_one()
    assert snapshots == 0


async def test_delete_personal_of_other_user_is_404(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    item = await make_catalog_item(
        db_session, country=ctx.refs.ukraine, title="Своя А", year=2021, created_by=ctx.id_a
    )
    response = await client.delete(f"/api/v1/catalog/{item.id}", headers=auth(ctx.token_b))
    assert response.status_code == 404


async def test_archive_flow(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    shared = await make_catalog_item(db_session, country=refs.ukraine, title="Спільна", year=2020)
    personal = await make_catalog_item(
        db_session, country=refs.ukraine, title="Своя", year=2021, created_by=ctx.id_a
    )
    shared_id, personal_id = shared.id, personal.id

    by_user = await client.post(
        f"/api/v1/catalog/{shared_id}/archive",
        json={"reason": "duplicate"},
        headers=auth(ctx.token_a),
    )
    assert by_user.status_code == 403

    empty_reason = await client.post(
        f"/api/v1/catalog/{shared_id}/archive",
        json={"reason": "  "},
        headers=auth(ctx.token_b),
    )
    assert empty_reason.status_code == 400

    on_personal = await client.post(
        f"/api/v1/catalog/{personal_id}/archive",
        json={"reason": "no"},
        headers=auth(ctx.token_b),
    )
    # B does not see A's personal item at all.
    assert on_personal.status_code == 404

    own_personal = await client.post(
        f"/api/v1/catalog/{personal_id}/archive",
        json={"reason": "no"},
        headers=auth(ctx.token_a),
    )
    assert own_personal.status_code == 400

    archived = await client.post(
        f"/api/v1/catalog/{shared_id}/archive",
        json={"reason": "duplicate"},
        headers=auth(ctx.token_b),
    )
    assert archived.status_code == 200
    body = archived.json()
    assert body["isArchived"] is True
    assert body["archiveReason"] == "duplicate"
    assert body["archivedAt"] is not None

    twice = await client.post(
        f"/api/v1/catalog/{shared_id}/archive",
        json={"reason": "again"},
        headers=auth(ctx.token_b),
    )
    assert twice.status_code == 409

    # Gone from the shop window for everyone.
    listing = await client.get("/api/v1/catalog", headers=auth(ctx.token_a))
    assert shared_id not in {row["id"] for row in listing.json()["items"]}

    unarchived = await client.post(
        f"/api/v1/catalog/{shared_id}/unarchive", headers=auth(ctx.token_b)
    )
    assert unarchived.status_code == 200
    assert unarchived.json()["isArchived"] is False

    again = await client.post(f"/api/v1/catalog/{shared_id}/unarchive", headers=auth(ctx.token_b))
    assert again.status_code == 409

    audit_actions = (
        (
            await db_session.execute(
                select(AuditLog.action).where(AuditLog.entity_id == str(shared_id))
            )
        )
        .scalars()
        .all()
    )
    assert audit_actions == ["catalog_item.archive", "catalog_item.unarchive"]

    back = await client.get("/api/v1/catalog", headers=auth(ctx.token_a))
    assert shared_id in {row["id"] for row in back.json()["items"]}
