"""Reporting a background job run (docs/13-admin.md, part 1).

The reporter is a container, not a person: these cases cover the token, the
open/close pair and the awkward paths a nightly cron actually produces --
a run that dies before it can close itself, a retried close, a job that never
managed to open one.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import JOB_TOKEN

pytestmark = pytest.mark.asyncio

ENDPOINT = "/api/v1/internal/job-runs"
HEADERS = {"X-Job-Token": JOB_TOKEN}

FINISH = {
    "status": "ok",
    "runDate": "2026-09-10",
    "summary": (
        "update-prices ok series=8 scope=325 years=34 matched=321 "
        "inserted=321 corrected=0 dup=0 no_quote=4 no_link=0 errors=0"
    ),
    "stats": {"series": 8, "scope": 325, "matched": 321, "inserted": 321, "errors": 0},
    "exitCode": 0,
}


async def test_open_and_finish_a_run(client: AsyncClient) -> None:
    opened = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=HEADERS)
    assert opened.status_code == 201, opened.text
    run = opened.json()
    assert run["status"] == "running"
    assert run["finishedAt"] is None
    assert run["startedAt"] is not None

    closed = await client.patch(f"{ENDPOINT}/{run['id']}", json=FINISH, headers=HEADERS)
    assert closed.status_code == 200, closed.text
    finished = closed.json()
    assert finished["id"] == run["id"]
    assert finished["status"] == "ok"
    assert finished["finishedAt"] is not None
    assert finished["exitCode"] == 0
    assert finished["stats"]["inserted"] == 321
    assert finished["runDate"] == "2026-09-10"
    # A good run says its one line and nothing more (docs/13-admin.md, 2.4).
    assert finished["details"] is None


async def test_a_run_that_never_closed_stays_running(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reason the row is opened up front: a container killed mid-run
    leaves this behind, and 'running' since yesterday is the signal."""
    opened = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=HEADERS)
    run_id = opened.json()["id"]

    row = await db_session.execute(
        text("SELECT status, finished_at FROM job_runs WHERE id = :id"), {"id": run_id}
    )
    status_word, finished_at = row.one()
    assert status_word == "running"
    assert finished_at is None


async def test_a_failed_run_carries_its_details(client: AsyncClient) -> None:
    opened = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=HEADERS)
    closed = await client.patch(
        f"{ENDPOINT}/{opened.json()['id']}",
        json={
            "status": "failed",
            "summary": "update-prices failed series=0 scope=0 errors=1",
            "details": "reading the catalog: OperationalError: connection refused",
            "exitCode": 2,
        },
        headers=HEADERS,
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "failed"
    assert "connection refused" in closed.json()["details"]


async def test_a_job_may_post_an_already_finished_run(client: AsyncClient) -> None:
    """When opening the run failed but the work went on, the closing report
    is all we get -- it must not be lost for want of a row to attach to."""
    response = await client.post(ENDPOINT, json={"job": "update-prices", **FINISH}, headers=HEADERS)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "ok"
    assert run["finishedAt"] is not None


async def test_closing_twice_is_allowed(client: AsyncClient) -> None:
    """A retry after a network error repeats the same close."""
    opened = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=HEADERS)
    run_id = opened.json()["id"]
    first = await client.patch(f"{ENDPOINT}/{run_id}", json=FINISH, headers=HEADERS)
    second = await client.patch(f"{ENDPOINT}/{run_id}", json=FINISH, headers=HEADERS)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "ok"


async def test_unknown_run_is_not_found(client: AsyncClient) -> None:
    response = await client.patch(f"{ENDPOINT}/424242", json=FINISH, headers=HEADERS)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "headers",
    [pytest.param({}, id="no-token"), pytest.param({"X-Job-Token": "wrong"}, id="wrong-token")],
)
async def test_reporting_requires_the_token(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=headers)
    assert response.status_code == 401


async def test_the_job_name_is_validated(client: AsyncClient) -> None:
    response = await client.post(ENDPOINT, json={"job": "Update Prices!"}, headers=HEADERS)
    assert response.status_code == 422


async def test_a_run_cannot_be_closed_with_running(client: AsyncClient) -> None:
    opened = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=HEADERS)
    response = await client.patch(
        f"{ENDPOINT}/{opened.json()['id']}", json={"status": "running"}, headers=HEADERS
    )
    assert response.status_code == 422


async def test_reporting_is_refused_when_no_token_is_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset secret switches the endpoint off rather than letting anything
    through -- the failure mode of a forgotten variable must not be an open
    door."""
    from app.core import config

    monkeypatch.setenv("JOB_REPORT_TOKEN", "")
    config.get_settings.cache_clear()
    try:
        response = await client.post(ENDPOINT, json={"job": "update-prices"}, headers=HEADERS)
        assert response.status_code == 503
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()
