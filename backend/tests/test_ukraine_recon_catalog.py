"""Reading our own catalogue for the reconnaissance (app/ukraine_recon/catalog.py).

Shared Ukrainian items only: personal positions and other countries stay out,
archived items stay in (flagged), the latest central price snapshot and the
presence of photos come along.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import MediaFile, User
from app.models.enums import MediaRole, MediaSource
from app.ukraine_recon.catalog import CatalogSnapshot, load_catalog
from tests.helpers import unique_email
from tests.seed import add_snapshot, make_catalog_item, seed_reference


async def test_load_catalog_reads_shared_ukrainian_items_only(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    ref = await seed_reference(db_session)
    owner = User(email=unique_email(), password_hash=hash_password("x" * 12), email_verified=True)
    db_session.add(owner)
    await db_session.commit()

    shared = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Десятинная церковь",
        year=1996,
        denomination=ref.uah_2,
        series=ref.fauna,
        source_key="ucoin:ru.ucoin.net/coin/ukraine-2-hryvni-1996",
    )
    archived = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Дубль",
        year=1996,
        is_archived=True,
        archive_reason="duplicate",
    )
    await make_catalog_item(
        db_session, country=ref.ukraine, title="Личная", year=2000, created_by=owner.id
    )
    await make_catalog_item(db_session, country=ref.usa, title="Lincoln cent", year=1990)

    await add_snapshot(db_session, shared, "100.00", observed_at=datetime(2026, 1, 1, tzinfo=UTC))
    await add_snapshot(
        db_session,
        shared,
        "250.00",
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        source_url="https://www.ua-coins.info/ua/list/10-desyatynna-tserkva",
    )
    # A personal snapshot must not become "our" price.
    await add_snapshot(
        db_session,
        shared,
        "999.00",
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        created_by=owner.id,
    )
    db_session.add(
        MediaFile(
            catalog_item_id=shared.id,
            role=MediaRole.OBVERSE,
            source=MediaSource.UCOIN,
            external_url="https://example.test/obverse.jpg",
        )
    )
    await db_session.commit()

    snapshot = await load_catalog(db_session)

    assert snapshot.country_id == ref.ukraine.id
    titles = {item.title_original for item in snapshot.items}
    assert titles == {"Десятинная церковь", "Дубль"}
    entry = next(item for item in snapshot.items if item.id == shared.id)
    assert entry.denomination == Decimal("2")
    assert entry.denomination_label == "2 гривні"
    assert entry.series_name == "Флора і фауна"
    assert entry.last_price == Decimal("250.00")
    assert entry.source_key == "ucoin:ru.ucoin.net/coin/ukraine-2-hryvni-1996"
    # The ua-coins reference comes from the price snapshot, not from the row.
    assert entry.source_url == "https://www.ua-coins.info/ua/list/10-desyatynna-tserkva"
    assert entry.source_links == []
    assert entry.last_price_source == "UA-Coins"
    assert entry.has_photo is True
    assert entry.photo_sources == ["ucoin"]
    assert entry.match_keys() == ["2|1996|десятинная церковь"]
    assert next(item for item in snapshot.items if item.id == archived.id).is_archived

    counts = {series.name_original: series for series in snapshot.series}
    assert counts["Флора і фауна"].item_count == 1
    assert counts["Флора і фауна"].active_item_count == 1
    assert counts["Міста України"].item_count == 0

    # The JSON round trip is what lets the triangulation run without a database.
    path = tmp_path / "catalog.json"
    snapshot.write(path)
    restored = CatalogSnapshot.read(path)
    assert [item.to_dict() for item in restored.items] == [
        item.to_dict() for item in snapshot.items
    ]
    assert [s.to_dict() for s in restored.series] == [s.to_dict() for s in snapshot.series]
