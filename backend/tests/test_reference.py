"""Reference endpoints: countries, denominations, currencies."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import register_and_verify
from tests.seed import seed_reference


async def test_reference_endpoints_require_auth(client: AsyncClient) -> None:
    for path in ("/api/v1/countries", "/api/v1/denominations", "/api/v1/currencies"):
        response = await client.get(path)
        assert response.status_code == 401, path


async def test_countries_sorted_by_name(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    refs = await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)

    response = await client.get("/api/v1/countries", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    names = [row["name"] for row in response.json()]
    assert names == sorted(names)
    ukraine = next(row for row in response.json() if row["id"] == refs.ukraine.id)
    assert ukraine == {
        "id": refs.ukraine.id,
        "code": "UA",
        "name": "Україна",
        "nameRu": None,
        "nameEn": None,
        "collectVariants": False,
    }


async def test_denominations_filtered_by_country(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list
) -> None:
    refs = await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(
        f"/api/v1/denominations?countryId={refs.ukraine.id}", headers=headers
    )
    assert response.status_code == 200
    labels = [row["label"] for row in response.json()]
    assert labels == ["2 гривні", "5 гривень"]

    everything = await client.get("/api/v1/denominations", headers=headers)
    assert len(everything.json()) == 3


async def test_currencies(client: AsyncClient, db_session: AsyncSession, mail_outbox: list) -> None:
    await seed_reference(db_session)
    _, token = await register_and_verify(client, mail_outbox)

    response = await client.get("/api/v1/currencies", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    codes = [row["code"] for row in response.json()]
    assert codes == ["EUR", "UAH", "USD"]
    uah = next(row for row in response.json() if row["code"] == "UAH")
    assert uah == {"code": "UAH", "name": "Hryvnia", "symbol": "₴", "decimalPlaces": 2}
