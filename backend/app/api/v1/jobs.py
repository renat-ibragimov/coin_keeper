"""Job run reporting: the machine-facing side of the admin section.

Not under /admin -- nobody signs in here. The caller is a scheduled job in a
container of its own, authenticated by a shared token (docs/13-admin.md).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AppSettings, DbSession, JobToken, Telegram
from app.api.errors import ProblemError
from app.core.telegram import TelegramSender
from app.core.telegram.messages import job_run_message
from app.models.jobs import JobRun
from app.repositories.telegram import TelegramRecipientRepository
from app.schemas.jobs import JobRunFinishIn, JobRunIn, JobRunOut
from app.services.jobs import JobRunNotFoundError, JobRunService
from app.services.telegram import admin_url, notify_job_run

router = APIRouter(prefix="/internal/job-runs", tags=["jobs"])


async def _queue_report(
    background: BackgroundTasks,
    session: AsyncSession,
    settings: AppSettings,
    sender: TelegramSender,
    run: JobRun,
) -> None:
    """Send the run to every linked chat once the reporter has its answer.

    The chat ids are read here, inside the request, because the background
    task runs after the session is closed; the sending itself is plain HTTP
    and must not make a night's work wait on telegram.
    """
    if run.status == "running":
        return
    chat_ids = await TelegramRecipientRepository(session).all_chat_ids()
    if not chat_ids:
        return
    text = job_run_message(run, admin_url=admin_url(settings))
    background.add_task(notify_job_run, sender, chat_ids, text)


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_job_run(
    session: DbSession,
    _: JobToken,
    settings: AppSettings,
    sender: Telegram,
    background: BackgroundTasks,
    payload: JobRunIn,
) -> JobRunOut:
    run = await JobRunService(session).open_run(payload)
    await _queue_report(background, session, settings, sender, run)
    return JobRunOut.model_validate(run)


@router.patch("/{run_id}")
async def finish_job_run(
    session: DbSession,
    _: JobToken,
    settings: AppSettings,
    sender: Telegram,
    background: BackgroundTasks,
    run_id: int,
    payload: JobRunFinishIn,
) -> JobRunOut:
    try:
        run = await JobRunService(session).finish_run(run_id, payload)
    except JobRunNotFoundError as exc:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "job-run-not-found",
            "Not found",
            "No job run with this id.",
        ) from exc
    await _queue_report(background, session, settings, sender, run)
    return JobRunOut.model_validate(run)
