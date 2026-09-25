"""Migration 0027 on a database filled at 0026.

Every existing refresh token is retired (one forced sign-in for everyone), and
each row gets the new family and session columns filled in.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import _admin_url, _database_url, _run_alembic_to

# 9701 is a live session, 9702 one that was already rotated away.
FIXTURE = """
INSERT INTO users (id, email, email_verified, is_active)
VALUES (970, 'migration-0027@example.com', true, true);

INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at)
VALUES (9701, 970, 'hash-live', now() + interval '30 days', '2026-09-01 10:00+00');

INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, revoked_at, created_at)
VALUES (9702, 970, 'hash-rotated', now() + interval '30 days', '2026-09-02 10:00+00',
        '2026-09-01 09:00+00');
"""

QUERY = """
SELECT revoked_at IS NOT NULL AS revoked, revoke_reason, family_id IS NOT NULL AS has_family,
       session_started_at = created_at AS started_at_created, persistent
FROM refresh_tokens WHERE id = :token_id
"""


@pytest.fixture(scope="module")
async def migrated_connection() -> AsyncIterator[AsyncConnection]:
    db_name = f"coinkeeper_0027_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    url = _database_url(db_name)
    try:
        await asyncio.to_thread(_run_alembic_to, "0026", url)
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            for statement in filter(None, (s.strip() for s in FIXTURE.split(";"))):
                await connection.execute(text(statement))
        await engine.dispose()

        await asyncio.to_thread(_run_alembic_to, "0027", url)

        engine = create_async_engine(url)
        async with engine.connect() as connection:
            yield connection
        await engine.dispose()
    finally:
        admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


async def row(connection: AsyncConnection, token_id: int) -> dict[str, object]:
    result = await connection.execute(text(QUERY), {"token_id": token_id})
    return dict(result.mappings().one())


async def test_a_live_session_is_retired(migrated_connection: AsyncConnection) -> None:
    assert await row(migrated_connection, 9701) == {
        "revoked": True,
        "revoke_reason": "logout_all",
        "has_family": True,
        "started_at_created": True,
        "persistent": True,
    }


async def test_an_already_revoked_token_replays_as_a_plain_401(
    migrated_connection: AsyncConnection,
) -> None:
    """`logout_all`, not `rotated`: a legacy token coming back after the
    migration must not be taken for theft."""
    assert (await row(migrated_connection, 9702))["revoke_reason"] == "logout_all"
