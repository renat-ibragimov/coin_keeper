"""roll-series: series_id copied onto "Ми сильні. Ми разом." siblings that lack one.

No NBU card ever gives this series a canonical name (app/ukraine_pipeline/
series.py cannot see it, gaps.py refuses to create the coin at all — see both
modules' docstrings), so every record enters by hand and this step only
propagates the series_id a person already set once.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem
from app.ukraine_pipeline import roll_series
from tests.seed import country_by_code, make_catalog_item, make_series, seed_currencies

TITLE = "Ми сильні. Ми разом."


async def test_roll_series_copies_series_from_a_sibling(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    series = await make_series(db_session, country=country, name=TITLE.rstrip("."))
    linked = await make_catalog_item(
        db_session,
        country=country,
        title=f"{TITLE} Одеська область",
        year=2022,
        series=series,
    )
    unlinked = await make_catalog_item(
        db_session,
        country=country,
        title=f"{TITLE} Запорізька область",
        year=2026,
    )

    outcome = await roll_series.backfill_series(db_session, country_id=country.id, dry_run=False)

    assert outcome.series_id == series.id
    assert outcome.updated == [{"itemId": unlinked.id, "title": unlinked.title_original}]
    updated = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.id == unlinked.id))
    ).scalar_one()
    assert updated.series_id == series.id
    # The record that already had a series is left exactly as it was.
    untouched = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.id == linked.id))
    ).scalar_one()
    assert untouched.series_id == series.id


async def test_roll_series_dry_run_writes_nothing(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    series = await make_series(db_session, country=country, name=TITLE.rstrip("."))
    await make_catalog_item(
        db_session, country=country, title=f"{TITLE} Одеська область", year=2022, series=series
    )
    unlinked = await make_catalog_item(
        db_session, country=country, title=f"{TITLE} Запорізька область", year=2026
    )

    outcome = await roll_series.backfill_series(db_session, country_id=country.id, dry_run=True)

    assert outcome.series_id == series.id
    assert len(outcome.updated) == 1
    untouched = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.id == unlinked.id))
    ).scalar_one()
    assert untouched.series_id is None


async def test_roll_series_second_run_has_nothing_left_to_do(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    series = await make_series(db_session, country=country, name=TITLE.rstrip("."))
    await make_catalog_item(
        db_session, country=country, title=f"{TITLE} Одеська область", year=2022, series=series
    )
    await make_catalog_item(
        db_session, country=country, title=f"{TITLE} Запорізька область", year=2026
    )

    await roll_series.backfill_series(db_session, country_id=country.id, dry_run=False)
    second = await roll_series.backfill_series(db_session, country_id=country.id, dry_run=False)

    assert second.updated == []


async def test_roll_series_ignores_unrelated_titles(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    series = await make_series(db_session, country=country, name=TITLE.rstrip("."))
    await make_catalog_item(
        db_session, country=country, title=f"{TITLE} Одеська область", year=2022, series=series
    )
    other = await make_catalog_item(
        db_session, country=country, title="Області України. Одеська область", year=2018
    )

    outcome = await roll_series.backfill_series(db_session, country_id=country.id, dry_run=False)

    assert outcome.updated == []
    untouched = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.id == other.id))
    ).scalar_one()
    assert untouched.series_id is None


async def test_roll_series_reports_when_nothing_to_copy_from(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    await make_catalog_item(
        db_session, country=country, title=f"{TITLE} Запорізька область", year=2026
    )

    outcome = await roll_series.backfill_series(db_session, country_id=country.id, dry_run=False)

    assert outcome.series_id is None
    assert outcome.updated == []
    assert outcome.problem is not None
