"""User analytics and role management in the admin section."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models import AuditLog, User
from app.models.enums import UserRole
from tests.helpers import register_and_verify
from tests.seed import add_collection_item, make_catalog_item, promote_to_admin, seed_reference

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class AdminAccount:
    id: int
    email: str
    token: str


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> AdminAccount:
    email, token = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, email)
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    return AdminAccount(id=user.id, email=user.email, token=token)


async def test_user_analytics_count_accounts_and_collectors(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    admin: AdminAccount,
) -> None:
    collector_email, _ = await register_and_verify(client, mail_outbox)
    collector = (
        await db_session.execute(select(User).where(User.email == collector_email))
    ).scalar_one()
    refs = await seed_reference(db_session)
    catalog_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Analytics coin", year=2026
    )
    await add_collection_item(db_session, owner_id=collector.id, item=catalog_item, quantity=3)

    response = await client.get("/api/v1/admin/users", headers=auth(admin.token))

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"totalUsers": 2, "collectors": 1}
    by_email = {item["email"]: item for item in body["items"]}
    assert by_email[collector_email]["coinCount"] == 3
    assert by_email[admin.email]["coinCount"] == 0


async def test_admin_promotes_a_user_by_stable_id(
    client: AsyncClient,
    db_session: AsyncSession,
    mail_outbox: list[EmailMessage],
    admin: AdminAccount,
) -> None:
    email, _ = await register_and_verify(client, mail_outbox)
    target = (await db_session.execute(select(User).where(User.email == email))).scalar_one()

    response = await client.patch(
        f"/api/v1/admin/users/{target.id}/role",
        json={"role": "admin"},
        headers=auth(admin.token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    await db_session.refresh(target)
    assert target.role == UserRole.ADMIN
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "role.promote", AuditLog.entity_id == str(target.id)
            )
        )
    ).scalar_one()
    assert audit.user_id == admin.id


async def test_admin_cannot_demote_self(client: AsyncClient, admin: AdminAccount) -> None:
    response = await client.patch(
        f"/api/v1/admin/users/{admin.id}/role",
        json={"role": "user"},
        headers=auth(admin.token),
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("cannot-demote-self")


async def test_regular_user_cannot_read_or_change_users(
    client: AsyncClient, mail_outbox: list[EmailMessage], admin: AdminAccount
) -> None:
    _, token = await register_and_verify(client, mail_outbox)
    listing = await client.get("/api/v1/admin/users", headers=auth(token))
    change = await client.patch(
        f"/api/v1/admin/users/{admin.id}/role",
        json={"role": "user"},
        headers=auth(token),
    )
    assert listing.status_code == change.status_code == 403
