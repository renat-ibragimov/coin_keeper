"""Reading job runs in the admin section (docs/13-admin.md, part 1)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from tests.conftest import JOB_TOKEN
from tests.helpers import register_and_verify
from tests.seed import promote_to_admin

pytestmark = pytest.mark.asyncio

REPORT = "/api/v1/internal/job-runs"
ADMIN_JOBS = "/api/v1/admin/jobs"
JOB_HEADERS = {"X-Job-Token": JOB_TOKEN}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def report_run(client: AsyncClient, job: str = "update-prices", **finish: object) -> int:
    opened = await client.post(REPORT, json={"job": job}, headers=JOB_HEADERS)
    run_id = int(opened.json()["id"])
    if finish:
        closed = await client.patch(f"{REPORT}/{run_id}", json=finish, headers=JOB_HEADERS)
        assert closed.status_code == 200, closed.text
    return run_id


@pytest.fixture
async def admin_token(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> str:
    email, token = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, email)
    return token


async def test_admin_sees_runs_newest_first(client: AsyncClient, admin_token: str) -> None:
    await report_run(client, status="ok", summary="first", exitCode=0)
    await report_run(client, status="failed", summary="second", exitCode=2)

    response = await client.get(ADMIN_JOBS, headers=auth(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [item["summary"] for item in body["items"]] == ["second", "first"]
    assert body["jobs"] == ["update-prices"]


async def test_runs_can_be_filtered_by_job(client: AsyncClient, admin_token: str) -> None:
    await report_run(client, "update-prices", status="ok")
    await report_run(client, "nbu-catalog-sync", status="ok")

    response = await client.get(
        ADMIN_JOBS, params={"job": "nbu-catalog-sync"}, headers=auth(admin_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["job"] == "nbu-catalog-sync"
    # The filter list still offers both, or the screen could not switch back.
    assert body["jobs"] == ["nbu-catalog-sync", "update-prices"]


async def test_a_single_run_carries_its_details(client: AsyncClient, admin_token: str) -> None:
    run_id = await report_run(
        client,
        status="partial",
        summary="update-prices partial errors=2",
        details="years NOT downloaded (2): 1996, 1997",
        stats={"errors": 2, "inserted": 12},
        exitCode=1,
    )

    response = await client.get(f"{ADMIN_JOBS}/{run_id}", headers=auth(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "partial"
    assert body["stats"]["errors"] == 2
    assert "1996" in body["details"]


async def test_unknown_run_is_not_found(client: AsyncClient, admin_token: str) -> None:
    response = await client.get(f"{ADMIN_JOBS}/424242", headers=auth(admin_token))
    assert response.status_code == 404


async def test_a_regular_user_is_refused(
    client: AsyncClient, mail_outbox: list[EmailMessage]
) -> None:
    await report_run(client, status="ok")
    _, token = await register_and_verify(client, mail_outbox)

    listing = await client.get(ADMIN_JOBS, headers=auth(token))
    assert listing.status_code == 403
    assert listing.json()["type"].endswith("admin-required")


async def test_an_anonymous_caller_is_refused(client: AsyncClient) -> None:
    response = await client.get(ADMIN_JOBS)
    assert response.status_code == 401
