"""Reads and writes over job_runs (docs/13-admin.md)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jobs import JobRun


class JobRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: JobRun) -> JobRun:
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_by_id(self, run_id: int) -> JobRun | None:
        result = await self._session.execute(select(JobRun).where(JobRun.id == run_id))
        return result.scalar_one_or_none()

    async def list_runs(
        self, *, job: str | None, limit: int, offset: int
    ) -> tuple[list[JobRun], int]:
        """Newest first: the admin list answers "did last night go well?"."""
        query = select(JobRun)
        count_query = select(func.count()).select_from(JobRun)
        if job is not None:
            query = query.where(JobRun.job == job)
            count_query = count_query.where(JobRun.job == job)

        total = await self._session.scalar(count_query) or 0
        result = await self._session.execute(
            query.order_by(JobRun.started_at.desc(), JobRun.id.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    async def known_jobs(self) -> list[str]:
        """Job names that have actually reported, for the filter on screen."""
        result = await self._session.execute(select(JobRun.job).distinct().order_by(JobRun.job))
        return list(result.scalars().all())
