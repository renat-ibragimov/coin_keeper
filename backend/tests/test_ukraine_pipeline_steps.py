"""The steps that write: gaps, titles, series, photos, prices.

Against the real schema, with the network mocked. Each test states one promise
of the step it covers: gaps creates coins and not products, titles takes the
issuer's wording, photos falls back from the National Bank to ua-coins and
never downloads the same image twice, prices flags what fails the checks.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CoinSeries, MarketPriceSnapshot, MediaFile, PriceSourceLink
from app.models.enums import CollectionGroup, MediaRole, MediaSource, TranslationSource
from app.ukraine_pipeline import bridge, gaps, photos, prices, series, titles
from app.ukraine_pipeline.catalog import load_items, ukraine_country_id
from app.ukraine_pipeline.lexicon import load_lexicon
from app.ukraine_pipeline.sources import NbuEnglish, Sources
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SourceRecord
from app.ukraine_recon.triangulate import Cluster, cluster_records
from tests.seed import country_by_code, make_catalog_item, seed_currencies

LEXICON = load_lexicon()
NBU_IMAGE = "https://bank.gov.ua/files/coins_images/A1{side}.png"
UA_COINS_IMAGE = "https://www.ua-coins.info/images/coins/middle/77_{side}.webp"


class RecordingStorage:
    """Stands in for MinIO: records keys instead of talking to S3."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self.objects[key] = payload

    def ensure_bucket(self) -> None:
        return None


def png_bytes(side: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (side, side), (200, 170, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def nbu_record(
    source_id: str = "1",
    *,
    title: str = "Соня садова",
    year: int = 1999,
    denomination: str = "2",
    series_name: str | None = "Флора і фауна України",
    kind: str = "coin",
    with_images: bool = True,
    material: str | None = "Нейзильбер, 12.8g, ø 31mm",
) -> SourceRecord:
    return SourceRecord(
        source=SOURCE_NBU,
        source_id=source_id,
        title_uk=title,
        denomination=Decimal(denomination),
        denomination_label=f"{denomination} гривень",
        year=year,
        issue_date=f"{year}-05-12",
        mintage=50_000,
        metal=material,
        series=series_name,
        kind=kind,
        url="https://bank.gov.ua/ua/uah/numismatic-products/souvenier-coins",
        image_urls=(
            [NBU_IMAGE.format(side="a"), NBU_IMAGE.format(side="r")] if with_images else []
        ),
        extra={
            "nbuId": source_id,
            "thumbnails": [f"https://bank.gov.ua/media/coins/{source_id}/avers.jpg"],
        },
    )


def ua_coins_record(
    source_id: str = "77",
    *,
    title: str = "Соня садова",
    year: int = 1999,
    denomination: str = "2",
    price: str | None = "450",
) -> SourceRecord:
    return SourceRecord(
        source=SOURCE_UA_COINS,
        source_id=source_id,
        title_uk=title,
        denomination=Decimal(denomination),
        year=year,
        price=None if price is None else Decimal(price),
        price_date="18.05.2026",
        url=f"https://www.ua-coins.info/ua/list/{source_id}-sonya",
        extra={"trend": "up"},
    )


def sources_of(*records: SourceRecord, english: dict[str, NbuEnglish] | None = None) -> Sources:
    found = Sources(
        nbu=[r for r in records if r.source == SOURCE_NBU],
        ua_coins=[r for r in records if r.source == SOURCE_UA_COINS],
        nbu_english=english or {},
    )
    found.clusters = cluster_records(found.by_source())
    return found


def only_cluster(found: Sources) -> Cluster:
    return found.clusters[0]


@pytest.fixture
def mock_client(tmp_path: Path) -> PoliteClient:
    """Every image URL answers with a PNG of the size that host really serves."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "bank.gov.ua" in request.url.host:
            return httpx.Response(200, content=png_bytes(1600))
        if "ua-coins.info" in request.url.host:
            return httpx.Response(200, content=png_bytes(600))
        return httpx.Response(404)

    return PoliteClient(
        cache_dir=tmp_path / "cache",
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )


# ----------------------------------------------------------------------- gaps
async def test_gaps_creates_coins_and_not_products(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    found = sources_of(
        nbu_record("1", title="Соня садова"),
        nbu_record("2", title="Набір монет", kind="set"),
        english={"1": NbuEnglish(title="Garden Dormouse", series="Ukrainian Flora and Fauna")},
    )

    outcome = await gaps.create_missing(
        db_session, country_id=country.id, sources=found, linked_keys=set(), dry_run=False
    )
    await db_session.commit()

    assert outcome.summary()["created"] == 1
    assert outcome.skipped_not_coin == 1
    created = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.source_key == "nbu:1"))
    ).scalar_one()
    assert created.title_original == "Соня садова"
    assert created.title_uk == "Соня садова"
    assert created.title_en == "Garden Dormouse"
    assert created.title_en_source is TranslationSource.OFFICIAL
    assert created.original_lang == "uk"
    assert created.created_by is None
    assert created.collection_group is CollectionGroup.COMMEMORATIVE
    assert created.mintage_announced == 50_000
    # The material string became a dictionary row plus two numbers.
    assert created.composition_id is not None
    assert created.weight_grams == Decimal("12.800")
    assert created.diameter_mm == Decimal("31.00")
    assert created.denomination_id is not None


async def test_gaps_does_not_create_the_same_coin_twice(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    found = sources_of(nbu_record("1"))

    for _ in range(2):
        outcome = await gaps.create_missing(
            db_session, country_id=country.id, sources=found, linked_keys=set(), dry_run=False
        )
        await db_session.commit()
    assert outcome.summary()["created"] == 0
    assert outcome.skipped_existing == 1
    total = (
        (await db_session.execute(select(CatalogItem).where(CatalogItem.source_key == "nbu:1")))
        .scalars()
        .all()
    )
    assert len(total) == 1


async def test_gaps_leaves_a_coin_we_already_linked_alone(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    found = sources_of(nbu_record("1"))
    outcome = await gaps.create_missing(
        db_session,
        country_id=country.id,
        sources=found,
        linked_keys={"nbu:1"},
        dry_run=False,
    )
    assert outcome.summary()["created"] == 0


# --------------------------------------------------------------------- titles
async def test_titles_take_the_issuer_wording(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня садовая", year=1999)
    found = sources_of(
        nbu_record("1", title='"Соня садова" у сувенірному пакованні (н)'),
        english={"1": NbuEnglish(title="Garden Dormouse", series=None)},
    )

    outcome = await titles.apply_titles(
        db_session,
        pairs={item.id: only_cluster(found)},
        sources=found,
        lexicon=LEXICON,
        dry_run=False,
    )
    await db_session.commit()

    assert outcome.summary()["updated"] == 1
    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    # No metal marker, no packaging phrase, no quotation marks.
    assert stored.title_original == "Соня садова"
    assert stored.title_uk == "Соня садова"
    assert stored.title_uk_source is TranslationSource.OFFICIAL
    assert stored.title_en == "Garden Dormouse"
    assert stored.original_lang == "uk"


async def test_titles_run_twice_change_nothing_the_second_time(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня садовая", year=1999)
    found = sources_of(nbu_record("1"))
    pairs = {item.id: only_cluster(found)}

    first = await titles.apply_titles(
        db_session, pairs=pairs, sources=found, lexicon=LEXICON, dry_run=False
    )
    await db_session.commit()
    second = await titles.apply_titles(
        db_session, pairs=pairs, sources=found, lexicon=LEXICON, dry_run=False
    )
    assert first.updated == 1
    assert second.updated == 0 and second.unchanged == 1


async def test_a_dry_run_writes_nothing(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня садовая", year=1999)
    found = sources_of(nbu_record("1"))

    outcome = await titles.apply_titles(
        db_session,
        pairs={item.id: only_cluster(found)},
        sources=found,
        lexicon=LEXICON,
        dry_run=True,
    )
    await db_session.commit()

    assert outcome.updated == 1
    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_original == "Соня садовая"


# --------------------------------------------------------------------- series
async def test_series_take_the_nbu_names(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    db_session.add(CoinSeries(country_id=country.id, name_original="Флора і фауна"))
    db_session.add(CoinSeries(country_id=country.id, name_original="сил"))
    await db_session.commit()

    found = sources_of(nbu_record("1", series_name="Флора і фауна України"))
    outcome = await series.rename_series(
        db_session,
        country_id=country.id,
        nbu_records=found.nbu,
        nbu_english={"1": NbuEnglish(title="x", series="Ukrainian Flora and Fauna")},
        dry_run=False,
    )
    await db_session.commit()

    names = {
        row.name_original: row
        for row in (
            await db_session.execute(select(CoinSeries).where(CoinSeries.country_id == country.id))
        ).scalars()
    }
    assert "Флора і фауна України" in names
    assert names["Флора і фауна України"].name_en == "Ukrainian Flora and Fauna"
    assert names["Флора і фауна України"].name_uk_source is TranslationSource.OFFICIAL
    # "сил" is a fragment of a title the importer stored as a series.
    assert "сил" not in names
    assert outcome.summary()["renamed"] == 1
    assert outcome.summary()["deleted"] == 1


async def test_a_bucket_is_taken_off_its_coins_but_they_are_kept(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    bucket = CoinSeries(country_id=country.id, name_original="Государство Украина (1992 - 2026)")
    db_session.add(bucket)
    await db_session.flush()
    item = await make_catalog_item(
        db_session, country=country, title="1 копійка", year=1992, series=bucket
    )
    await db_session.commit()

    await series.rename_series(
        db_session, country_id=country.id, nbu_records=[], nbu_english={}, dry_run=False
    )
    await db_session.commit()

    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.series_id is None


# --------------------------------------------------------------------- photos
async def test_photos_prefer_the_issuer_and_fall_back_to_ua_coins(
    db_session: AsyncSession, mock_client: PoliteClient
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    official = await make_catalog_item(db_session, country=country, title="Офіційна", year=2020)
    borrowed = await make_catalog_item(db_session, country=country, title="Запозичена", year=2019)

    with_photo = sources_of(nbu_record("1", year=2020), ua_coins_record("77", year=2020))
    without_photo = sources_of(
        nbu_record("2", title="Запозичена", year=2019, with_images=False),
        ua_coins_record("78", title="Запозичена", year=2019),
    )
    storage = RecordingStorage()

    with mock_client as client:
        outcome = await photos.download_photos(
            db_session,
            client=client,
            storage=storage,
            pairs={
                official.id: only_cluster(with_photo),
                borrowed.id: only_cluster(without_photo),
            },
            sources=with_photo,
            dry_run=False,
            limit=None,
            log=lambda _message: None,
        )
    await db_session.commit()

    assert outcome.from_nbu == 2
    assert outcome.from_ua_coins == 2
    rows = {
        (row.catalog_item_id, str(row.role)): row
        for row in (await db_session.execute(select(MediaFile))).scalars()
    }
    issuer = rows[(official.id, "obverse")]
    assert issuer.source is MediaSource.NBU
    assert issuer.attribution == "Національний банк України"
    assert issuer.variants is not None
    assert set(issuer.variants) == {"300", "600", "1200"}
    assert all(key in storage.objects for key in issuer.variants.values())

    # ua-coins serves 600 px, so there is no 1200 px form to store.
    second_best = rows[(borrowed.id, "obverse")]
    assert second_best.source is MediaSource.UA_COINS
    assert second_best.attribution == "ua-coins.info"
    assert second_best.variants is not None
    assert set(second_best.variants) == {"300", "600"}


async def test_photos_are_not_downloaded_twice(
    db_session: AsyncSession, mock_client: PoliteClient
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня", year=1999)
    found = sources_of(nbu_record("1"))
    pairs = {item.id: only_cluster(found)}
    storage = RecordingStorage()

    with mock_client as client:
        first = await photos.download_photos(
            db_session,
            client=client,
            storage=storage,
            pairs=pairs,
            sources=found,
            dry_run=False,
            limit=None,
            log=lambda _message: None,
        )
        await db_session.commit()
        second = await photos.download_photos(
            db_session,
            client=client,
            storage=storage,
            pairs=pairs,
            sources=found,
            dry_run=False,
            limit=None,
            log=lambda _message: None,
        )
    assert first.stored == 2
    assert second.stored == 0
    assert second.already_stored == 1


async def test_only_the_ukrainian_ucoin_hotlinks_go(db_session: AsyncSession) -> None:
    """A link we never downloaded and may not show is not worth keeping."""
    await seed_currencies(db_session)
    ukraine = await country_by_code(db_session, "UA")
    usa = await country_by_code(db_session, "US")
    ours = await make_catalog_item(db_session, country=ukraine, title="Соня", year=1999)
    theirs = await make_catalog_item(db_session, country=usa, title="Morgan Dollar", year=1899)
    db_session.add_all(
        [
            MediaFile(
                catalog_item_id=ours.id,
                role=MediaRole.OBVERSE,
                source=MediaSource.UCOIN,
                external_url="https://i.ucoin.net/coin/ua-obverse.jpg",
            ),
            MediaFile(
                catalog_item_id=theirs.id,
                role=MediaRole.OBVERSE,
                source=MediaSource.UCOIN,
                external_url="https://i.ucoin.net/coin/us-obverse.jpg",
            ),
            MediaFile(
                catalog_item_id=ours.id,
                role=MediaRole.REVERSE,
                source=MediaSource.UCOIN,
                storage_key="catalog/1/reverse/downloaded_600.webp",
            ),
        ]
    )
    await db_session.commit()

    removed = await photos.drop_ucoin_links(db_session, [ours.id], dry_run=False)
    await db_session.commit()

    assert removed == 1
    left = (await db_session.execute(select(MediaFile))).scalars().all()
    # The American hotlink and our own downloaded file both stay.
    assert {row.catalog_item_id for row in left} == {ours.id, theirs.id}
    assert len(left) == 2


# --------------------------------------------------------------------- prices
async def test_a_price_is_recorded_once_per_day(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня", year=1999)
    found = sources_of(nbu_record("1"), ua_coins_record("77"))
    pairs = {item.id: only_cluster(found)}

    first = await prices.record_prices(db_session, pairs=pairs, currencies=["UAH"], dry_run=False)
    await db_session.commit()
    second = await prices.record_prices(db_session, pairs=pairs, currencies=["UAH"], dry_run=False)
    await db_session.commit()

    assert first.written == 1 and second.written == 0
    assert second.already_recorded == 1
    snapshot = (
        await db_session.execute(
            select(MarketPriceSnapshot).where(MarketPriceSnapshot.catalog_item_id == item.id)
        )
    ).scalar_one()
    assert snapshot.source == "UA-Coins"
    assert snapshot.created_by is None
    assert snapshot.is_suspect is False
    assert snapshot.price == Decimal("450.00")
    assert snapshot.observed_at == datetime(2026, 5, 18, tzinfo=UTC)


async def test_a_price_that_fails_the_checks_is_kept_but_flagged(
    db_session: AsyncSession,
) -> None:
    """The history is worth having; a suspect snapshot stays out of the value."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня", year=1999)
    # The price is this coin's own year — the strongest sign of a parser slip.
    found = sources_of(nbu_record("1"), ua_coins_record("77", price="1999"))

    outcome = await prices.record_prices(
        db_session, pairs={item.id: only_cluster(found)}, currencies=["UAH"], dry_run=False
    )
    await db_session.commit()

    assert outcome.suspect == 1
    assert "looks_like_year" in outcome.by_rule
    snapshot = (
        await db_session.execute(
            select(MarketPriceSnapshot).where(MarketPriceSnapshot.catalog_item_id == item.id)
        )
    ).scalar_one()
    assert snapshot.is_suspect is True


async def test_a_coin_without_a_price_is_counted_not_invented(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня", year=1999)
    found = sources_of(nbu_record("1"), ua_coins_record("77", price=None))

    outcome = await prices.record_prices(
        db_session, pairs={item.id: only_cluster(found)}, currencies=["UAH"], dry_run=False
    )
    assert outcome.written == 0
    assert outcome.without_price == 1


# --------------------------------------------------------------------- bridge
async def test_links_are_written_once_and_updated_in_place(
    db_session: AsyncSession,
) -> None:
    """price_source_links holds one row per source; a second run rewrites it."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Соня", year=1999)
    found = sources_of(nbu_record("1"), ua_coins_record("77"))
    outcome = bridge.BridgeOutcome(
        linked=[
            bridge.Decision(
                item=(await load_items(db_session, country.id))[0],
                cluster=only_cluster(found),
                strategy="score",
                score=100.0,
            )
        ]
    )

    assert await bridge.write_links(db_session, outcome) == 2
    await db_session.commit()
    assert await bridge.write_links(db_session, outcome) == 2
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                select(PriceSourceLink).where(PriceSourceLink.catalog_item_id == item.id)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(row.source for row in rows) == ["NBU", "UA-Coins"]
    assert await bridge.linked_pairs(db_session, [item.id]) == {
        item.id: {
            SOURCE_NBU: "1",
            SOURCE_UA_COINS: "https://www.ua-coins.info/ua/list/77-sonya",
        }
    }


# -------------------------------------------------------------------- reading
async def test_our_side_is_read_with_its_links(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    await make_catalog_item(db_session, country=country, title="Соня", year=1999)
    await db_session.commit()

    country_id = await ukraine_country_id(db_session)
    assert country_id == country.id
    items = await load_items(db_session, country_id)
    assert [item.title_original for item in items] == ["Соня"]
    assert items[0].is_commemorative
