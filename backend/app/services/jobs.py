"""Job run reporting: a scheduled job tells the application what it did.

The reporter is the job itself, running elsewhere -- the nightly price step
lives in the coin-parser repository and its own container (docs/13-admin.md).
It opens a run before starting and closes it with the outcome, so this service
is deliberately thin: it stores what it is told and does not second-guess the
counters.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jobs import RUNNING, JobRun
from app.repositories.jobs import JobRunRepository
from app.schemas.jobs import JobRunFinishIn, JobRunIn

logger = logging.getLogger("app.jobs")


class JobRunNotFoundError(Exception):
    """No run with that id: 404."""


class JobRunService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = JobRunRepository(session)

    async def open_run(self, payload: JobRunIn) -> JobRun:
        finished = payload.status != RUNNING
        now = datetime.now(UTC)
        run = JobRun(
            job=payload.job,
            status=payload.status,
            started_at=payload.started_at or now,
            # The CHECK constraint ties the two together, and a job posting an
            # already finished run has no separate finishing time to give.
            finished_at=now if finished else None,
            run_date=payload.run_date,
            summary=payload.summary,
            stats=payload.stats,
            details=payload.details,
            exit_code=payload.exit_code,
        )
        await self._repo.add(run)
        logger.info("job run %s opened for %s (%s)", run.id, run.job, run.status)
        return run

    async def finish_run(self, run_id: int, payload: JobRunFinishIn) -> JobRun:
        """Close a run. Closing an already closed one is allowed on purpose:
        the reporter may retry after a network error, and a repeat carrying
        the same outcome is not an error worth failing a night's work over."""
        run = await self._repo.get_by_id(run_id)
        if run is None:
            raise JobRunNotFoundError(run_id)

        run.status = payload.status
        run.finished_at = datetime.now(UTC)
        run.summary = payload.summary
        run.stats = payload.stats
        run.details = payload.details
        run.exit_code = payload.exit_code
        if payload.run_date is not None:
            run.run_date = payload.run_date

        logger.info("job run %s finished: %s", run.id, run.summary or run.status)
        return run
