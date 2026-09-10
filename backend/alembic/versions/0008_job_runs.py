"""job_runs: what a background job did, in a table the admin section can read.

The nightly ua-coins price run already reports itself -- it prints a summary
line and returns a meaningful exit code -- but only into a log file on the
server that nobody opens. This table is where that report lands instead.

One row per run. It opens as 'running' before the work starts and is closed
with the outcome afterwards, so a run that died halfway leaves a row stuck in
'running' rather than no trace at all. The status words are the ones the
parser already uses ('ok', 'partial', 'failed'); only 'running' is ours.

`stats` keeps the counters as the job reported them, without this schema
having to know what a given job counts. `details` stays empty on a good run:
per docs/13-admin.md the report is one line unless something went wrong.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_CHECK = "ck_job_runs_status_valid"
FINISHED_CHECK = "ck_job_runs_finished_with_status"


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        # The day the run is *about*, which is not the same as the day it ran:
        # the nightly step is dated by the ua-coins table header.
        sa.Column("run_date", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("stats", postgresql.JSONB(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_check_constraint(
        STATUS_CHECK,
        "job_runs",
        "status IN ('running', 'ok', 'partial', 'failed')",
    )
    # A finished run has a finishing time and an unfinished one does not:
    # the admin list tells "still going" from "died" by exactly this.
    op.create_check_constraint(
        FINISHED_CHECK,
        "job_runs",
        "(status = 'running') = (finished_at IS NULL)",
    )
    op.create_index("ix_job_runs_job_started_at", "job_runs", ["job", sa.text("started_at DESC")])
    op.execute(
        "CREATE TRIGGER job_runs_set_updated_at BEFORE UPDATE ON job_runs "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS job_runs_set_updated_at ON job_runs")
    op.drop_index("ix_job_runs_job_started_at", table_name="job_runs")
    op.drop_table("job_runs")
