"""Upgrade an existing 0020 database without losing its users."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from tests.conftest import _admin_url, _database_url, _run_alembic_to


@pytest.fixture(scope="module")
async def migrated_connection() -> AsyncIterator[AsyncConnection]:
    db_name = f"coinkeeper_admin_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin.dispose()

    url = _database_url(db_name)
    try:
        await asyncio.to_thread(_run_alembic_to, "0020", url)
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                INSERT INTO users (email, password_hash, role, email_verified)
                VALUES ('migration-admin@example.com', 'unused', 'admin', true)
            """)
            )
        await engine.dispose()

        await asyncio.to_thread(_run_alembic_to, "head", url)

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


async def test_upgrade_preserves_users_and_accepts_admin_records(
    migrated_connection: AsyncConnection,
) -> None:
    connection = migrated_connection
    assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024"
    user_id = await connection.scalar(
        text("SELECT id FROM users WHERE email = 'migration-admin@example.com'")
    )
    assert user_id is not None
    await connection.execute(
        text("INSERT INTO job_runs (job, status, started_at) VALUES ('prices', 'running', now())")
    )
    await connection.execute(
        text("INSERT INTO telegram_recipients (user_id, chat_id) VALUES (:user_id, 12345)"),
        {"user_id": user_id},
    )
    await connection.execute(
        text("""
            INSERT INTO auth_tokens (user_id, kind, token_hash, expires_at)
            VALUES (:user_id, 'telegram_link', 'hash', now() + interval '15 minutes')
        """),
        {"user_id": user_id},
    )
    assert await connection.scalar(text("SELECT count(*) FROM job_runs")) == 1
    await connection.rollback()
