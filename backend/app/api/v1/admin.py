"""Admin section endpoints (docs/13-admin.md).

Everything here is behind the admin role. Reading job runs is the first thing
it gives: the nightly price run used to be visible only in a log file on the
server.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, AppSettings, DbSession, Pagination
from app.api.errors import ProblemError
from app.repositories.jobs import JobRunRepository
from app.schemas.jobs import JobRunOut, JobRunsOut
from app.schemas.telegram import TelegramLinkOut, TelegramStatusOut
from app.services.telegram import BotNotConfiguredError, TelegramLinkService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs")
async def list_job_runs(
    session: DbSession,
    _: AdminUser,
    pagination: Pagination,
    job: Annotated[str | None, Query()] = None,
) -> JobRunsOut:
    repo = JobRunRepository(session)
    runs, total = await repo.list_runs(
        job=job, limit=pagination.page_size, offset=pagination.offset
    )
    return JobRunsOut(
        items=[JobRunOut.model_validate(run) for run in runs],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        jobs=await repo.known_jobs(),
    )


@router.get("/jobs/{run_id}")
async def get_job_run(session: DbSession, _: AdminUser, run_id: int) -> JobRunOut:
    run = await JobRunRepository(session).get_by_id(run_id)
    if run is None:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "job-run-not-found",
            "Not found",
            "No job run with this id.",
        )
    return JobRunOut.model_validate(run)


@router.get("/telegram")
async def telegram_status(
    session: DbSession, user: AdminUser, settings: AppSettings
) -> TelegramStatusOut:
    chats = await TelegramLinkService(session, settings).list_chats(user)
    return TelegramStatusOut(connected=bool(chats), chats=len(chats))


@router.post("/telegram/link")
async def create_telegram_link(
    session: DbSession, user: AdminUser, settings: AppSettings
) -> TelegramLinkOut:
    """A one-time code wrapped in a t.me link. Pressing Start in that chat is
    what actually connects it (docs/13-admin.md, 2.5)."""
    try:
        url, expires_at = await TelegramLinkService(session, settings).create_link(user)
    except BotNotConfiguredError as exc:
        raise ProblemError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "telegram-not-configured",
            "Service unavailable",
            "The admin bot is not configured on this server.",
        ) from exc
    return TelegramLinkOut(url=url, expires_at=expires_at)


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(session: DbSession, user: AdminUser, settings: AppSettings) -> None:
    await TelegramLinkService(session, settings).unlink(user)
