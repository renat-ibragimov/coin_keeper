"""Test fixtures.

Test database: a throwaway database on the Postgres instance the developer
already runs through docker compose, created once per session and migrated with
Alembic. The reasoning is in backend/README.md; the short version is that
running the real migration is itself part of what we want covered, and
testcontainers would add a docker-in-docker dependency to CI for no extra
signal.

Every test runs inside a transaction that is rolled back afterwards, so tests
neither see nor leave state behind.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from alembic import command
from app.core.mail.base import EmailMessage
from app.core.mail.console import ConsoleMailBackend

BACKEND_ROOT = Path(__file__).resolve().parent.parent

ADMIN_URL_ENV = "TEST_POSTGRES_ADMIN_URL"
DEFAULT_ADMIN_URL = "postgresql+asyncpg://coinkeeper:devpass@localhost:5432/postgres"
DEFAULT_REDIS_URL = "redis://localhost:6379/15"


class RecordingMailBackend(ConsoleMailBackend):
    """The console backend plus a list the tests can read.

    Deliberately a subclass: the message still goes through the real console
    path, so the test exercises what runs locally and in CI.
    """

    def __init__(self, outbox: list[EmailMessage]) -> None:
        self._outbox = outbox

    async def send(self, message: EmailMessage) -> None:
        await super().send(message)
        self._outbox.append(message)


def _admin_url() -> str:
    return os.environ.get(ADMIN_URL_ENV, DEFAULT_ADMIN_URL)


def _database_url(db_name: str) -> str:
    return f"{_admin_url().rsplit('/', 1)[0]}/{db_name}"


def _configure_environment(url: str) -> None:
    """Point the application at the test database before it reads settings."""
    os.environ["DATABASE_URL"] = url
    os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", DEFAULT_REDIS_URL)
    os.environ["JWT_SECRET"] = "test-secret-not-used-anywhere-else"
    os.environ["PUBLIC_BASE_URL"] = "http://testserver"
    os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
    os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
    os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
    os.environ["COOKIE_SECURE"] = "false"
    # Tests must never send real email. A test that would is a broken test.
    os.environ["MAIL_BACKEND"] = "console"

    from app.core.config import get_settings

    get_settings.cache_clear()


def _run_migrations() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def database_url() -> AsyncIterator[str]:
    """Create a fresh database, migrate it, drop it at the end."""
    db_name = f"coinkeeper_test_{uuid.uuid4().hex[:12]}"

    admin_engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    await admin_engine.dispose()

    url = _database_url(db_name)
    _configure_environment(url)
    await asyncio.to_thread(_run_migrations)

    yield url

    admin_engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": db_name},
        )
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    await admin_engine.dispose()


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """One transaction per test, always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield connection
        await transaction.rollback()


@pytest.fixture
async def db_session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    yield session
    await session.close()


@pytest.fixture
async def redis_client() -> AsyncIterator[None]:
    """Flushed around every test: rate limit counters must not leak between cases."""
    from app.core.rate_limit import close_redis, get_redis

    await get_redis().flushdb()
    yield
    await get_redis().flushdb()
    await close_redis()


@pytest.fixture
def mail_outbox() -> list[EmailMessage]:
    return []


@pytest.fixture
async def client(
    db_session: AsyncSession,
    redis_client: None,
    mail_outbox: list[EmailMessage],
) -> AsyncIterator[AsyncClient]:
    from app.core.mail import get_mail_backend
    from app.db.session import get_db_session
    from app.main import create_app

    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        # Mirrors app.db.session.get_db_session, rollback included: a route that
        # raises must undo its writes here exactly as it does in production.
        # Without the rollback, side effects on error paths look persisted when
        # in reality they are discarded.
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_mail_backend] = lambda: RecordingMailBackend(mail_outbox)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()
