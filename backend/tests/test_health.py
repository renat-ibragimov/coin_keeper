"""Health endpoint (docs/10-infra.md)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_reports_every_component(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    body = response.json()

    assert set(body) == {"status", "database", "redis", "storage"}
    assert body["database"]["status"] == "ok"
    assert body["redis"]["status"] == "ok"
    # Storage may be unreachable when MinIO is not running; the endpoint must
    # still answer and say which component is down rather than crash.
    assert body["storage"]["status"] in {"ok", "error"}

    expected_status = 200 if body["storage"]["status"] == "ok" else 503
    assert response.status_code == expected_status
