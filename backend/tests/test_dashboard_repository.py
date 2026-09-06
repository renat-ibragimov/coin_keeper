"""DashboardRepository.series_breakdown: ordering and limit (docs/11-roadmap.md)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dashboard import DashboardRepository
from tests.seed import (
    add_collection_item,
    make_catalog_item,
    make_series,
    make_user,
    seed_reference,
)


@pytest.fixture
async def ctx(db_session: AsyncSession) -> SimpleNamespace:
    refs = await seed_reference(db_session)
    user = await make_user(db_session, email="dashboard-repo@example.com")
    return SimpleNamespace(refs=refs, user_id=user.id)


async def test_series_with_owned_coins_outranks_bigger_empty_series(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """A user's own coins must reach the dashboard even when their series
    are small next to the shared catalog's biggest ones."""
    refs = ctx.refs
    small = await make_series(db_session, country=refs.ukraine, name="Мала серія")
    item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=small
    )
    await add_collection_item(db_session, owner_id=ctx.user_id, item=item, price="10")

    for index in range(10):
        big = await make_series(db_session, country=refs.ukraine, name=f"Велика серія {index}")
        for year in range(2000, 2005):
            await make_catalog_item(
                db_session,
                country=refs.ukraine,
                title=f"Монета {index}-{year}",
                year=year,
                series=big,
            )

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()

    assert rows[0].name == "Мала серія"
    assert rows[0].owned == 1


async def test_more_complete_owned_series_ranks_first(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    mostly_done = await make_series(db_session, country=refs.ukraine, name="Майже готово")
    half_done = await make_series(db_session, country=refs.ukraine, name="Наполовину")

    for series, owned_count in ((mostly_done, 3), (half_done, 2)):
        for i in range(4):
            item = await make_catalog_item(
                db_session,
                country=refs.ukraine,
                title=f"{series.name_original} {i}",
                year=2010 + i,
                series=series,
            )
            if i < owned_count:
                await add_collection_item(db_session, owner_id=ctx.user_id, item=item, price="10")

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()
    by_name = {row.name: row for row in rows}

    assert by_name["Майже готово"].owned == 3
    assert by_name["Наполовину"].owned == 2
    names_in_order = [row.name for row in rows]
    assert names_in_order.index("Майже готово") < names_in_order.index("Наполовину")


async def test_a_completed_owned_series_does_not_push_out_an_unfinished_one(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    for index in range(11):
        series = await make_series(db_session, country=refs.ukraine, name=f"Завершена {index}")
        item = await make_catalog_item(
            db_session,
            country=refs.ukraine,
            title=f"Готова монета {index}",
            year=2020,
            series=series,
        )
        await add_collection_item(db_session, owner_id=ctx.user_id, item=item, price="10")

    unfinished = await make_series(db_session, country=refs.ukraine, name="Незавершена")
    owned_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Є в колекції", year=2020, series=unfinished
    )
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Відсутня", year=2021, series=unfinished
    )
    await add_collection_item(db_session, owner_id=ctx.user_id, item=owned_item, price="10")

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()

    assert len(rows) == 12
    names = {row.name for row in rows}
    assert "Незавершена" in names


async def test_user_without_coins_keeps_the_biggest_series_first(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Regression guard for the empty-state dashboard (docs/11-roadmap.md)."""
    refs = ctx.refs
    small = await make_series(db_session, country=refs.ukraine, name="Мала")
    big = await make_series(db_session, country=refs.ukraine, name="Велика")
    await make_catalog_item(db_session, country=refs.ukraine, title="М1", year=2010, series=small)
    for i in range(3):
        await make_catalog_item(
            db_session, country=refs.ukraine, title=f"В{i}", year=2010 + i, series=big
        )

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()
    by_name = {row.name: row for row in rows}

    assert all(row.owned == 0 for row in rows)
    names_in_order = [row.name for row in rows]
    assert names_in_order.index("Велика") < names_in_order.index("Мала")
    assert by_name["Велика"].count == 3
