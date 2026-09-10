"""Wire types for background job runs (docs/13-admin.md)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

# Lowercase, dash-separated, matching the step names the parser already uses
# on its command line ("update-prices").
JOB_NAME_PATTERN = r"^[a-z][a-z0-9-]{1,63}$"

FinishedStatus = Literal["ok", "partial", "failed"]


class JobRunIn(CamelModel):
    """Opening report: sent before the work starts.

    A job that could not open its run -- the API was down for a moment -- may
    also post an already finished one, which is why the final fields are
    accepted here too.
    """

    job: str = Field(pattern=JOB_NAME_PATTERN)
    status: Literal["running", "ok", "partial", "failed"] = "running"
    started_at: datetime | None = None
    run_date: date | None = None
    summary: str | None = Field(default=None, max_length=1000)
    stats: dict[str, object] | None = None
    details: str | None = Field(default=None, max_length=20000)
    exit_code: int | None = Field(default=None, ge=0, le=255)


class JobRunFinishIn(CamelModel):
    """Closing report: the outcome, the counters and, when it went badly, why."""

    status: FinishedStatus
    run_date: date | None = None
    summary: str | None = Field(default=None, max_length=1000)
    stats: dict[str, object] | None = None
    details: str | None = Field(default=None, max_length=20000)
    exit_code: int | None = Field(default=None, ge=0, le=255)


class JobRunOut(CamelModel):
    id: int
    job: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    run_date: date | None
    summary: str | None
    stats: dict[str, object] | None
    details: str | None
    exit_code: int | None
