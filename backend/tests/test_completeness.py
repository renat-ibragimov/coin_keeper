"""Completeness grouped by an arbitrary catalog field: series, year,
denomination, material, edge, quality — generalizing the retired per-series
summary/items routes (see tests/test_series.py for what stayed
series-only)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail.base import EmailMessage
from app.models.enums import MetalKind
from tests.helpers import register_and_verify
from tests.seed import (
    add_collection_item,
    add_snapshot,
    make_catalog_item,
    make_edge_type,
    make_material,
    make_quality_type,
    make_series,
    promote_to_admin,
    seed_reference,
    set_country_active,
    set_country_catalog_confirmed,
    user_id_by_email,
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ctx(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> SimpleNamespace:
    """A is a regular user, B is an admin."""
    refs = await seed_reference(db_session)
    email_a, token_a = await register_and_verify(client, mail_outbox)
    email_b, token_b = await register_and_verify(client, mail_outbox)
    await promote_to_admin(db_session, email_b)
    return SimpleNamespace(
        refs=refs,
        token_a=token_a,
        id_a=await user_id_by_email(db_session, email_a),
        token_b=token_b,
        id_b=await user_id_by_email(db_session, email_b),
    )


async def test_group_completeness_rules(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Ported from the retired GET /series/{id}/summary: the same rules, now
    behind GET /completeness/group?groupBy=series."""
    refs = ctx.refs
    series = refs.fauna

    owned_twice = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=series
    )
    missing_priced = await make_catalog_item(
        db_session, country=refs.ukraine, title="Сова", year=2017, series=series
    )
    missing_unpriced = await make_catalog_item(
        db_session, country=refs.ukraine, title="Рись", year=2016, series=series
    )
    archived_with_coin = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Архівна",
        year=2015,
        series=series,
        is_archived=True,
        archive_reason="duplicate",
    )
    # Personal item of B in the same series: invisible to A entirely.
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Особиста Б",
        year=2014,
        series=series,
        created_by=ctx.id_b,
    )

    # Two instances of one item still count as one completed position.
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_twice, price="100")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_twice, price="120")
    # An instance of the archived item: money counts, completeness does not.
    await add_collection_item(db_session, owner_id=ctx.id_a, item=archived_with_coin, price="80")

    await add_snapshot(db_session, owned_twice, "150.00")
    await add_snapshot(db_session, missing_priced, "200.00")
    await add_snapshot(db_session, archived_with_coin, "500.00")
    # The only snapshot of the unpriced one is suspect: it stays unpriced.
    await add_snapshot(db_session, missing_unpriced, "77777.00", is_suspect=True)

    group = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={series.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    summary = group["summary"]

    # Active visible: owned_twice, missing_priced, missing_unpriced.
    assert summary["total"] == 3
    assert summary["owned"] == 1
    assert summary["missing"] == 2
    assert summary["completionPercent"] == 33.3
    # Money: 100 + 120 for the dolphin, 80 for the archived instance.
    assert summary["purchaseTotalUah"] == "300.00"
    # Value: 2 dolphins x 150 plus the archived coin at 500.
    assert summary["currentValueUah"] == "800.00"
    assert summary["unpricedMissing"] == 1
    assert group["label"] == series.name_original

    # For B the same series counts their own personal item as collectable.
    group_b = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={series.id}",
            headers=auth(ctx.token_b),
        )
    ).json()
    assert group_b["summary"]["total"] == 4
    assert group_b["summary"]["owned"] == 0
    assert group_b["summary"]["purchaseTotalUah"] == "0.00"


async def test_group_percent_never_exceeds_100(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Instances on archived items must not inflate the numerator."""
    refs = ctx.refs
    series = refs.cities
    active = await make_catalog_item(
        db_session, country=refs.ukraine, title="Київ", year=2020, series=series
    )
    archived = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Львів",
        year=2019,
        series=series,
        is_archived=True,
        archive_reason="withdrawn",
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=active, price="10")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=archived, price="10")

    summary = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={series.id}",
            headers=auth(ctx.token_a),
        )
    ).json()["summary"]
    assert summary["total"] == 1
    assert summary["owned"] == 1
    assert summary["completionPercent"] == 100.0


async def test_group_404_for_empty_group(client: AsyncClient, ctx: SimpleNamespace) -> None:
    response = await client.get(
        "/api/v1/completeness/group?groupBy=series&value=999999", headers=auth(ctx.token_a)
    )
    assert response.status_code == 404


async def test_group_own_price_snapshot_feeds_value(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, series=refs.fauna
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=item, price="100")
    await add_snapshot(db_session, item, "150.00", observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    # A's own newer snapshot overrides the shared one — for A only.
    await add_snapshot(
        db_session,
        item,
        "180.00",
        observed_at=datetime(2026, 2, 1, tzinfo=UTC),
        created_by=ctx.id_a,
        source="Manual",
    )

    group_a = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={refs.fauna.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    assert group_a["summary"]["currentValueUah"] == "180.00"


async def test_group_metal_kind_filter_narrows_the_summary(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The metalKind filter must also reach GET /completeness/group, not only
    /summary (docs/ui.md, "Completeness": carries its filters from the
    group list into the group's own detail screen)."""
    refs = ctx.refs
    series = refs.fauna
    gold = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Gold",
        year=2020,
        series=series,
        metal_kind=MetalKind.PRECIOUS,
    )
    steel = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Steel",
        year=2021,
        series=series,
        metal_kind=MetalKind.BASE,
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=gold, price="1000")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=steel, price="5")

    group = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={series.id}&metalKind=precious",
            headers=auth(ctx.token_a),
        )
    ).json()["summary"]
    assert group["total"] == 1
    assert group["owned"] == 1
    assert group["purchaseTotalUah"] == "1000.00"


async def test_items_metal_kind_and_owned_filters(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Same two filters on GET /completeness/items: metalKind narrows the
    dimension the same way /group and /summary do, and owned narrows the
    grid to what the user already has (or is still missing)."""
    refs = ctx.refs
    series = refs.fauna
    gold_owned = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Gold owned",
        year=2020,
        series=series,
        metal_kind=MetalKind.PRECIOUS,
    )
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Gold missing",
        year=2021,
        series=series,
        metal_kind=MetalKind.PRECIOUS,
    )
    steel_owned = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Steel owned",
        year=2022,
        series=series,
        metal_kind=MetalKind.BASE,
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=gold_owned, price="1000")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=steel_owned, price="5")
    headers_a = auth(ctx.token_a)

    by_metal = (
        await client.get(
            f"/api/v1/completeness/items?groupBy=series&value={series.id}&metalKind=precious",
            headers=headers_a,
        )
    ).json()
    assert {item["title"] for item in by_metal["items"]} == {"Gold owned", "Gold missing"}

    owned_only = (
        await client.get(
            f"/api/v1/completeness/items?groupBy=series&value={series.id}"
            "&metalKind=precious&owned=true",
            headers=headers_a,
        )
    ).json()
    assert {item["title"] for item in owned_only["items"]} == {"Gold owned"}

    missing_only = (
        await client.get(
            f"/api/v1/completeness/items?groupBy=series&value={series.id}&owned=false",
            headers=headers_a,
        )
    ).json()
    assert {item["title"] for item in missing_only["items"]} == {"Gold missing"}


async def test_items_of_an_unconfirmed_country_still_show(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The same rule the retired GET /series/{id}/items tested (BR-13a):
    GET /catalog?seriesId= is the harder gate and stays empty for a series of
    an unconfirmed country however much of it the user owns, while the
    completeness items endpoint (about the user's own collection) shows it."""
    refs = ctx.refs
    await set_country_catalog_confirmed(db_session, refs.usa, confirmed=False)

    series_usa = await make_series(db_session, country=refs.usa, name="50 State Quarters")
    owned_item = await make_catalog_item(
        db_session,
        country=refs.usa,
        title="Delaware",
        year=1999,
        series=series_usa,
        created_by=ctx.id_a,
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_item, price="10")

    headers_a = auth(ctx.token_a)

    items = await client.get(
        f"/api/v1/completeness/items?groupBy=series&value={series_usa.id}", headers=headers_a
    )
    assert items.status_code == 200
    body = items.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Delaware"

    via_catalog = await client.get(f"/api/v1/catalog?seriesId={series_usa.id}", headers=headers_a)
    assert via_catalog.json()["total"] == 0


async def test_summary_groups_by_year(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    owned_2020 = await make_catalog_item(db_session, country=refs.ukraine, title="A", year=2020)
    await make_catalog_item(db_session, country=refs.ukraine, title="B", year=2020)
    await make_catalog_item(db_session, country=refs.ukraine, title="C", year=2021)
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_2020, price="50")

    summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=year&countryId={refs.ukraine.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    by_value = {row["value"]: row for row in summary}
    assert by_value[2020]["label"] == "2020"
    assert by_value[2020]["unassigned"] is False
    assert by_value[2020]["summary"]["total"] == 2
    assert by_value[2020]["summary"]["owned"] == 1
    assert by_value[2021]["summary"]["total"] == 1
    assert by_value[2021]["summary"]["owned"] == 0


async def test_summary_metal_kind_filter_applies_to_every_dimension(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """The metalKind filter narrows any dimension's counts, not only the
    "metal" groupBy tab itself (docs/ui.md, "Completeness")."""
    refs = ctx.refs
    gold_2020 = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Gold",
        year=2020,
        metal_kind=MetalKind.PRECIOUS,
    )
    steel_2020 = await make_catalog_item(
        db_session, country=refs.ukraine, title="Steel", year=2020, metal_kind=MetalKind.BASE
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=gold_2020, price="1000")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=steel_2020, price="5")

    summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=year&countryId={refs.ukraine.id}"
            "&metalKind=precious",
            headers=auth(ctx.token_a),
        )
    ).json()
    by_value = {row["value"]: row for row in summary}
    assert by_value[2020]["summary"]["total"] == 1
    assert by_value[2020]["summary"]["owned"] == 1
    assert by_value[2020]["summary"]["purchaseTotalUah"] == "1000.00"


async def test_unassigned_bucket_for_denomination_and_material(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    copper_nickel = await make_material(
        db_session, code="cu-ni", name_uk="Мідно-нікелевий сплав", name_en="Copper-nickel"
    )

    with_denomination = await make_catalog_item(
        db_session, country=refs.ukraine, title="A", year=2020, denomination=refs.uah_2
    )
    without_denomination = await make_catalog_item(
        db_session, country=refs.ukraine, title="B", year=2020
    )
    with_material = await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="C",
        year=2020,
        composition_id=copper_nickel.id,
    )
    without_material = await make_catalog_item(
        db_session, country=refs.ukraine, title="D", year=2020
    )

    await add_collection_item(db_session, owner_id=ctx.id_a, item=without_denomination, price="5")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=without_material, price="5")

    denomination_summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=denomination&countryId={refs.ukraine.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    unassigned_row = next(row for row in denomination_summary if row["unassigned"])
    assert unassigned_row["value"] is None
    assert unassigned_row["label"] is None
    # Owned and without a denomination: "B" (no denomination, no material
    # either) and "D" (no material, but also no denomination) both land here.
    assert unassigned_row["summary"]["owned"] == 2
    assigned_row = next(row for row in denomination_summary if row["value"] == refs.uah_2.id)
    assert assigned_row["summary"]["total"] == 1

    unassigned_items = (
        await client.get(
            "/api/v1/completeness/items?groupBy=denomination&unassigned=true",
            headers=auth(ctx.token_a),
        )
    ).json()
    # "C" has a material but no denomination, so it lands here too.
    assert {item["title"] for item in unassigned_items["items"]} == {"B", "C", "D"}

    material_summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=material&countryId={refs.ukraine.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    material_unassigned = next(row for row in material_summary if row["unassigned"])
    # Owned and without a material: "B" and "D" again (neither has a
    # composition_id; "A" has neither a material nor an owned instance).
    assert material_unassigned["summary"]["owned"] == 2
    material_assigned = next(row for row in material_summary if row["value"] == copper_nickel.id)
    assert material_assigned["label"] == "Мідно-нікелевий сплав"
    assert material_assigned["summary"]["total"] == 1

    _ = with_denomination, with_material


async def test_unassigned_is_rejected_for_year(client: AsyncClient, ctx: SimpleNamespace) -> None:
    group = await client.get(
        "/api/v1/completeness/group?groupBy=year&unassigned=true", headers=auth(ctx.token_a)
    )
    assert group.status_code == 422

    items = await client.get(
        "/api/v1/completeness/items?groupBy=year&unassigned=true", headers=auth(ctx.token_a)
    )
    assert items.status_code == 422


async def test_group_requires_exactly_one_of_value_or_unassigned(
    client: AsyncClient, ctx: SimpleNamespace
) -> None:
    neither = await client.get(
        "/api/v1/completeness/group?groupBy=series", headers=auth(ctx.token_a)
    )
    assert neither.status_code == 422

    both = await client.get(
        "/api/v1/completeness/group?groupBy=series&value=1&unassigned=true",
        headers=auth(ctx.token_a),
    )
    assert both.status_code == 422


async def test_unassigned_bucket_for_edge_and_quality(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    refs = ctx.refs
    # Codes distinct from the app's own seeded edge/quality dictionaries
    # (app/reference_data/{edge_types,quality_types}.py) -- those already
    # populate this table, so "reeded"/"proof" would collide.
    reeded = await make_edge_type(
        db_session, code="test-reeded", name_uk="Рифлений", name_en="Reeded"
    )
    proof = await make_quality_type(db_session, code="test-proof", name_uk="Пруф", name_en="Proof")

    with_edge = await make_catalog_item(
        db_session, country=refs.ukraine, title="A", year=2020, edge_type_id=reeded.id
    )
    without_edge = await make_catalog_item(db_session, country=refs.ukraine, title="B", year=2020)
    with_quality = await make_catalog_item(
        db_session, country=refs.ukraine, title="C", year=2020, quality_type_id=proof.id
    )
    without_quality = await make_catalog_item(
        db_session, country=refs.ukraine, title="D", year=2020
    )

    await add_collection_item(db_session, owner_id=ctx.id_a, item=without_edge, price="5")
    await add_collection_item(db_session, owner_id=ctx.id_a, item=without_quality, price="5")

    edge_summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=edge&countryId={refs.ukraine.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    edge_unassigned = next(row for row in edge_summary if row["unassigned"])
    assert edge_unassigned["value"] is None
    assert edge_unassigned["label"] is None
    edge_assigned = next(row for row in edge_summary if row["value"] == reeded.id)
    assert edge_assigned["label"] == "Рифлений"
    assert edge_assigned["summary"]["total"] == 1

    unassigned_edge_items = (
        await client.get(
            "/api/v1/completeness/items?groupBy=edge&unassigned=true", headers=auth(ctx.token_a)
        )
    ).json()
    assert {item["title"] for item in unassigned_edge_items["items"]} == {"B", "C", "D"}

    quality_summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=quality&countryId={refs.ukraine.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    quality_assigned = next(row for row in quality_summary if row["value"] == proof.id)
    assert quality_assigned["label"] == "Пруф"
    assert quality_assigned["summary"]["total"] == 1

    quality_group = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=quality&value={proof.id}",
            headers=auth(ctx.token_a),
        )
    ).json()
    assert quality_group["summary"]["total"] == 1

    _ = with_edge, with_quality


async def test_group_value_must_be_an_integer(client: AsyncClient, ctx: SimpleNamespace) -> None:
    response = await client.get(
        "/api/v1/completeness/group?groupBy=series&value=not-a-number", headers=auth(ctx.token_a)
    )
    assert response.status_code == 422


async def test_a_draft_counts_nowhere_until_it_is_published(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """A draft from the NBU sync is invisible to completeness (BR-2): the
    fraction must count exactly the tiles the grid shows."""
    refs = ctx.refs
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Опублікована", year=2024, series=refs.fauna
    )
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Чернетка",
        year=2024,
        series=refs.fauna,
        status="draft",
    )
    headers = auth(ctx.token_a)

    summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=series&countryId={refs.ukraine.id}",
            headers=headers,
        )
    ).json()
    by_value = {row["value"]: row["summary"] for row in summary}
    assert by_value[refs.fauna.id]["total"] == 1

    group = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={refs.fauna.id}", headers=headers
        )
    ).json()
    assert group["summary"]["total"] == 1
    assert group["summary"]["unpricedMissing"] == 1

    items = (
        await client.get(
            f"/api/v1/completeness/items?groupBy=series&value={refs.fauna.id}", headers=headers
        )
    ).json()
    assert [row["title"] for row in items["items"]] == ["Опублікована"]


async def test_an_inactive_country_counts_only_what_the_user_owns(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """With no country picked, a shared record of an inactive country is not
    part of anyone's completeness unless they hold a coin of it (BR-13)."""
    refs = ctx.refs
    await set_country_active(db_session, refs.usa, active=False)
    await make_catalog_item(db_session, country=refs.ukraine, title="Україна", year=1999)
    owned_usa = await make_catalog_item(db_session, country=refs.usa, title="Delaware", year=1999)
    await make_catalog_item(db_session, country=refs.usa, title="Pennsylvania", year=1999)
    await add_collection_item(db_session, owner_id=ctx.id_a, item=owned_usa, price="10")
    headers = auth(ctx.token_a)

    summary = (
        await client.get("/api/v1/completeness/summary?groupBy=year", headers=headers)
    ).json()
    by_value = {row["value"]: row["summary"] for row in summary}
    assert by_value[1999]["total"] == 2
    assert by_value[1999]["owned"] == 1

    group = (
        await client.get("/api/v1/completeness/group?groupBy=year&value=1999", headers=headers)
    ).json()
    assert group["summary"]["total"] == 2

    items = (
        await client.get("/api/v1/completeness/items?groupBy=year&value=1999", headers=headers)
    ).json()
    assert sorted(row["title"] for row in items["items"]) == ["Delaware", "Україна"]


async def test_personal_positions_count_like_shared_ones(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """A collector's own coin that the catalogue lacks counts for its author,
    whatever its country, and for nobody else (BR-2)."""
    refs = ctx.refs
    await set_country_active(db_session, refs.usa, active=False)
    await make_catalog_item(
        db_session, country=refs.ukraine, title="Спільна", year=2001, series=refs.fauna
    )
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Моя особиста",
        year=2001,
        series=refs.fauna,
        created_by=ctx.id_a,
    )
    await make_catalog_item(
        db_session, country=refs.usa, title="My own quarter", year=2001, created_by=ctx.id_a
    )
    await make_catalog_item(
        db_session,
        country=refs.ukraine,
        title="Чужа особиста",
        year=2001,
        series=refs.fauna,
        created_by=ctx.id_b,
    )
    headers = auth(ctx.token_a)

    by_series = {
        row["value"]: row["summary"]
        for row in (
            await client.get(
                f"/api/v1/completeness/summary?groupBy=series&countryId={refs.ukraine.id}",
                headers=headers,
            )
        ).json()
    }
    assert by_series[refs.fauna.id]["total"] == 2

    by_year = {
        row["value"]: row["summary"]
        for row in (
            await client.get("/api/v1/completeness/summary?groupBy=year", headers=headers)
        ).json()
    }
    assert by_year[2001]["total"] == 3

    items = (
        await client.get("/api/v1/completeness/items?groupBy=year&value=2001", headers=headers)
    ).json()
    assert sorted(row["title"] for row in items["items"]) == [
        "My own quarter",
        "Моя особиста",
        "Спільна",
    ]


async def test_a_collected_series_of_an_inactive_country_counts_whole(
    client: AsyncClient, db_session: AsyncSession, ctx: SimpleNamespace
) -> None:
    """Once the user holds a coin of a series, its missing coins count and show
    even when the series' country is inactive — completeness is there to say
    what is missing (BR-13). A user with nothing from the series sees none of it."""
    refs = ctx.refs
    await set_country_active(db_session, refs.usa, active=False)
    series_usa = await make_series(db_session, country=refs.usa, name="Standing Liberty")
    quarter = await make_catalog_item(
        db_session, country=refs.usa, title="Quarter", year=1920, series=series_usa
    )
    await make_catalog_item(
        db_session, country=refs.usa, title="Dime", year=1921, series=series_usa
    )
    await add_collection_item(db_session, owner_id=ctx.id_a, item=quarter, price="10")
    headers_a = auth(ctx.token_a)
    headers_b = auth(ctx.token_b)

    summary = (
        await client.get(
            f"/api/v1/completeness/summary?groupBy=series&countryId={refs.usa.id}",
            headers=headers_a,
        )
    ).json()
    by_value = {row["value"]: row["summary"] for row in summary}
    assert by_value[series_usa.id]["total"] == 2
    assert by_value[series_usa.id]["owned"] == 1

    group = (
        await client.get(
            f"/api/v1/completeness/group?groupBy=series&value={series_usa.id}", headers=headers_a
        )
    ).json()
    assert group["summary"]["total"] == 2
    assert group["summary"]["missing"] == 1

    items = (
        await client.get(
            f"/api/v1/completeness/items?groupBy=series&value={series_usa.id}", headers=headers_a
        )
    ).json()
    assert [row["title"] for row in items["items"]] == ["Quarter", "Dime"]

    by_year = {
        row["value"]: row["summary"]
        for row in (
            await client.get("/api/v1/completeness/summary?groupBy=year", headers=headers_a)
        ).json()
    }
    assert by_year[1921]["total"] == 1
    assert by_year[1921]["owned"] == 0

    items_b = (
        await client.get(
            f"/api/v1/completeness/items?groupBy=series&value={series_usa.id}", headers=headers_b
        )
    ).json()
    assert items_b["total"] == 0
    by_year_b = {
        row["value"]
        for row in (
            await client.get("/api/v1/completeness/summary?groupBy=year", headers=headers_b)
        ).json()
    }
    assert 1921 not in by_year_b
