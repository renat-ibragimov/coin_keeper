from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.helpers import register_and_verify
from tests.seed import make_catalog_item, promote_to_admin, seed_reference

pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_draft_is_hidden_until_admin_approves_it(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
) -> None:
    refs = await seed_reference(db_session)
    _, user_token = await register_and_verify(client, mail_outbox)
    admin_email, admin_token = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, admin_email)
    draft = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Нова монета НБУ",
        year=2026,
        status="draft",
        source_key="nbu:9999",
    )

    listing = await client.get("/api/v1/catalog", headers=auth(user_token))
    assert draft.id not in {item["id"] for item in listing.json()["items"]}
    hidden = await client.get(f"/api/v1/catalog/{draft.id}", headers=auth(user_token))
    assert hidden.status_code == 404

    proposals = await client.get("/api/v1/admin/proposals", headers=auth(admin_token))
    assert proposals.status_code == 200, proposals.text
    assert [row["card"]["id"] for row in proposals.json()["items"]] == [draft.id]

    approved = await client.post(
        f"/api/v1/admin/proposals/{draft.id}/approve", headers=auth(admin_token)
    )
    assert approved.status_code == 200, approved.text
    visible = await client.get(f"/api/v1/catalog/{draft.id}", headers=auth(user_token))
    assert visible.status_code == 200


async def test_admin_can_reject_a_draft_without_deleting_it(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
) -> None:
    refs = await seed_reference(db_session)
    admin_email, admin_token = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, admin_email)
    draft = await make_catalog_item(
        db_session, country=refs.ukraine, title="Помилка", year=2026, status="draft"
    )

    rejected = await client.post(
        f"/api/v1/admin/proposals/{draft.id}/reject",
        headers=auth(admin_token),
        json={"reason": "дублікат"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["isArchived"] is True
    assert (await db_session.get(type(draft), draft.id)).status == "rejected"
