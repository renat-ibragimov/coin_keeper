"""DashboardRepository.series_breakdown: only started series, no cap.

"Мої серії" on the overview shows every series the owner has started at
least one coin of — the front end (`myCollectionSeries`) does its own sort
over the whole set and drops anything with `owned == 0`, so this repository
method restricts to `owned > 0` and does not otherwise rank or limit rows
(owner's call, 2026-09-12).
"""

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


async def test_a_series_with_no_owned_coins_is_left_out(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """A series the owner has not started at all never reaches the
    overview — however big it is next to the one they actually collect."""
    refs = ctx.refs
    started = await make_series(db_session, country=refs.ukraine, name="Почата серія")
    item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=started
    )
    await add_collection_item(db_session, owner_id=ctx.user_id, item=item, price="10")

    untouched = await make_series(db_session, country=refs.ukraine, name="Незаймана серія")
    for year in range(2000, 2010):
        await make_catalog_item(
            db_session, country=refs.ukraine, title=f"Монета {year}", year=year, series=untouched
        )

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()

    names = {row.name for row in rows}
    assert names == {"Почата серія"}


async def test_no_cap_on_how_many_started_series_are_returned(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """A cap here used to let several small, fully-completed series push a
    still-open one out of the response entirely — there is no cap now, the
    front end sorts the whole set itself."""
    refs = ctx.refs
    for index in range(20):
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

    assert len(rows) == 21
    names = {row.name for row in rows}
    assert "Незавершена" in names


async def test_count_is_the_series_total_not_just_what_is_owned(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The outer join must not shrink the denominator to the owned rows —
    `count` is every item in the series, `owned` is the owner's share of it."""
    refs = ctx.refs
    series = await make_series(db_session, country=refs.ukraine, name="Серія")
    owned_item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Є", year=2020, series=series
    )
    for year in (2021, 2022):
        await make_catalog_item(
            db_session, country=refs.ukraine, title=f"Немає {year}", year=year, series=series
        )
    await add_collection_item(db_session, owner_id=ctx.user_id, item=owned_item, price="10")

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()

    row = next(row for row in rows if row.name == "Серія")
    assert (row.count, row.owned) == (3, 1)


async def test_a_user_with_no_coins_gets_an_empty_breakdown(
    db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The empty state ("Ще не почато жодної серії") is a front-end concern
    over an empty list, not a fallback list of the biggest unowned series."""
    refs = ctx.refs
    series = await make_series(db_session, country=refs.ukraine, name="Серія")
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Монета", year=2018, series=series
    )

    repo = DashboardRepository(db_session, user_id=ctx.user_id)
    rows = await repo.series_breakdown()

    assert rows == []
