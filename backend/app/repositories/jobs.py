"""Reads and writes over job_runs (docs/13-admin.md)."""

from __future__ import annotations

from sqlalchemy import select
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
