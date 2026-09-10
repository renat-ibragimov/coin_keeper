"""Job run reporting: the machine-facing side of the admin section.

Not under /admin -- nobody signs in here. The caller is a scheduled job in a
container of its own, authenticated by a shared token (docs/13-admin.md).
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DbSession, JobToken
from app.api.errors import ProblemError
from app.schemas.jobs import JobRunFinishIn, JobRunIn, JobRunOut
from app.services.jobs import JobRunNotFoundError, JobRunService

router = APIRouter(prefix="/internal/job-runs", tags=["jobs"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_job_run(session: DbSession, _: JobToken, payload: JobRunIn) -> JobRunOut:
    run = await JobRunService(session).open_run(payload)
    return JobRunOut.model_validate(run)


@router.patch("/{run_id}")
async def finish_job_run(
    session: DbSession, _: JobToken, run_id: int, payload: JobRunFinishIn
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
    return JobRunOut.model_validate(run)
