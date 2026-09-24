"""The sentinel cron: alarms when an expected job never showed up.

docs/admin.md, 2.7. A run that finished badly already explains itself in
the chat the moment it closes (app/api/v1/jobs.py); this script exists for
the other failure -- a run that never opened at all, because the container
that schedules it is dead, cron itself never fired, or the network between it
and this API is gone. Nothing reports that on its own, so something has to
come and look.

No ARQ, on purpose (docs/admin.md, "Open questions", decided 2026-09-15):
this is a periodic check, not a queued task with retries, so a second cron
entry calling this script is the whole mechanism -- it will not move to ARQ
even once ARQ exists in the project for something else.

    docker compose exec -T api python scripts/watchdog.py

Silent on a clean bill of health, the same rule the chat already follows for
a good run: only trouble is worth a message.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.telegram import TelegramSender, build_telegram_sender
from app.core.telegram.messages import watchdog_message
from app.db.session import dispose_engine, get_session_factory
from app.repositories.jobs import JobRunRepository
from app.repositories.telegram import TelegramRecipientRepository
from app.services.telegram import broadcast_admin_message

# How stale a job's last run is allowed to get before it is an alarm, not a
# schedule. Tied to coin-parser's actual crontab (coin-parser/deploy/crontab),
# not guessed: each threshold is the job's own interval plus a few hours of
# slack for a late run, so an on-time job never trips this by chance -- move
# the threshold if the cron line moves.
EXPECTED_INTERVALS: dict[str, timedelta] = {
    "update-prices": timedelta(hours=26),  # daily at 07:10 UTC
    "update-rates": timedelta(hours=7),  # every 5 hours at :25
    "nbu-catalog-sync": timedelta(hours=26),  # daily at 10:40 UTC
}

EXIT_OK = 0


async def _check(
    session: AsyncSession,
    sender: TelegramSender,
    *,
    now: datetime | None = None,
) -> list[tuple[str, datetime | None]]:
    """Which jobs are overdue, and sends the alarm if any are.

    Returns the stale list so a caller (or a test) can see what happened
    without re-reading the chat.
    """
    moment = now or datetime.now(UTC)
    runs = JobRunRepository(session)

    stale: list[tuple[str, datetime | None]] = []
    for job, interval in EXPECTED_INTERVALS.items():
        recent, _ = await runs.list_runs(job=job, limit=1, offset=0)
        last_run = recent[0].started_at if recent else None
        if last_run is None or moment - last_run > interval:
            stale.append((job, last_run))

    if not stale:
        return stale

    chat_ids = await TelegramRecipientRepository(session).all_chat_ids()
    if chat_ids:
        await broadcast_admin_message(sender, chat_ids, watchdog_message(stale))
    return stale


async def main() -> int:
    settings = get_settings()
    sender = build_telegram_sender(settings)
    try:
        async with get_session_factory()() as session:
            stale = await _check(session, sender)
    finally:
        await dispose_engine()

    if not stale:
        print("[watchdog] all jobs are within their expected window")
        return EXIT_OK
    for job, last_run in stale:
        when = "never" if last_run is None else last_run.isoformat()
        print(f"[watchdog] {job}: overdue, last run {when}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
