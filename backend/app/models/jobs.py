"""Background job runs: one row per run of a scheduled job (docs/13-admin.md)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, updated_at_column

# The job names we expect to see. Kept as a plain tuple rather than an enum:
# a job is named by whoever schedules it, and a name this side has not heard
# of yet is a reason to look, not a reason to reject the report.
JOB_UPDATE_PRICES = "update-prices"

RUNNING = "running"
FINISHED_STATUSES = ("ok", "partial", "failed")
STATUSES = (RUNNING, *FINISHED_STATUSES)


class JobRun(Base):
    """What a background job did, as the job itself reported it.

    Opened before the work starts and closed with the outcome afterwards, so
    an interrupted run leaves a row stuck in 'running' instead of nothing.
    `stats` holds the job's own counters verbatim -- this table does not know
    what any particular job counts.
    """

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The day the run is about, not the day it ran: the nightly price step is
    # dated by the ua-coins table header, which may still be yesterday's.
    run_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # Empty on a good run: the report is one line unless something went wrong.
    details: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'partial', 'failed')", name="status_valid"),
        CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)", name="finished_with_status"
        ),
        Index("ix_job_runs_job_started_at", "job", text("started_at DESC")),
    )

    @property
    def is_finished(self) -> bool:
        return self.status != RUNNING
