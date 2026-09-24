"""The watchdog script: a job that never reported must not stay silent
(docs/admin.md, "Watchdog")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.jobs import JobRun
from app.models.telegram import TelegramRecipient
from app.models.user import User
from scripts.watchdog import EXPECTED_INTERVALS, _check
from tests.conftest import RecordingTelegramSender
from tests.helpers import unique_email

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


async def _add_run(session: AsyncSession, job: str, started_at: datetime) -> None:
    session.add(
        JobRun(
            job=job,
            status="ok",
            started_at=started_at,
            finished_at=started_at + timedelta(minutes=5),
            summary=f"{job} ok",
        )
    )
    await session.flush()


async def _link_admin_chat(session: AsyncSession, chat_id: int) -> None:
    user = User(
        email=unique_email(),
        password_hash="not-a-real-hash",
        role=UserRole.ADMIN,
        is_active=True,
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    session.add(TelegramRecipient(user_id=user.id, chat_id=chat_id))
    await session.flush()


async def test_everything_fresh_stays_silent(db_session: AsyncSession) -> None:
    for job, interval in EXPECTED_INTERVALS.items():
        await _add_run(db_session, job, NOW - interval + timedelta(minutes=1))
    await _link_admin_chat(db_session, 111)
    sender = RecordingTelegramSender()

    stale = await _check(db_session, sender, now=NOW)

    assert stale == []
    assert sender.sent == []


async def test_a_job_that_never_ran_is_stale(db_session: AsyncSession) -> None:
    # Only two of the three known jobs have ever reported.
    await _add_run(db_session, "update-prices", NOW - timedelta(hours=1))
    await _add_run(db_session, "update-rates", NOW - timedelta(hours=1))
    await _link_admin_chat(db_session, 222)
    sender = RecordingTelegramSender()

    stale = await _check(db_session, sender, now=NOW)

    assert stale == [("nbu-catalog-sync", None)]
    assert len(sender.sent) == 1
    assert sender.sent[0].chat_id == 222
    assert "Оновлення каталогу" in sender.sent[0].text
    assert "ще жодного разу" in sender.sent[0].text


async def test_an_overdue_job_is_stale(db_session: AsyncSession) -> None:
    stale_since = NOW - EXPECTED_INTERVALS["update-prices"] - timedelta(hours=1)
    await _add_run(db_session, "update-prices", stale_since)
    await _add_run(db_session, "update-rates", NOW - timedelta(hours=1))
    await _add_run(db_session, "nbu-catalog-sync", NOW - timedelta(hours=1))
    await _link_admin_chat(db_session, 333)
    sender = RecordingTelegramSender()

    stale = await _check(db_session, sender, now=NOW)

    assert [job for job, _ in stale] == ["update-prices"]
    assert len(sender.sent) == 1
    assert "Оновлення цін" in sender.sent[0].text
    assert stale_since.strftime("%Y-%m-%d %H:%M") in sender.sent[0].text


async def test_stale_with_no_linked_chat_sends_nothing(db_session: AsyncSession) -> None:
    """Detected either way -- only the notification depends on a linked chat."""
    sender = RecordingTelegramSender()

    stale = await _check(db_session, sender, now=NOW)

    assert len(stale) == len(EXPECTED_INTERVALS)
    assert sender.sent == []


async def test_a_run_still_in_progress_counts_by_its_start_time(db_session: AsyncSession) -> None:
    """A stuck 'running' row is exactly the case the watchdog should also
    catch -- it has a started_at like any other row, and no finish in sight."""
    stuck_since = NOW - EXPECTED_INTERVALS["nbu-catalog-sync"] - timedelta(hours=2)
    db_session.add(
        JobRun(job="nbu-catalog-sync", status="running", started_at=stuck_since, finished_at=None)
    )
    await db_session.flush()
    await _add_run(db_session, "update-prices", NOW - timedelta(hours=1))
    await _add_run(db_session, "update-rates", NOW - timedelta(hours=1))
    sender = RecordingTelegramSender()

    stale = await _check(db_session, sender, now=NOW)

    assert [job for job, _ in stale] == ["nbu-catalog-sync"]
