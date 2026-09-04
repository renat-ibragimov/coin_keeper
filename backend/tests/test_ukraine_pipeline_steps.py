"""The steps that write: gaps, repair-gaps, merge, titles, series, photos, prices.

Against the real schema, with the network mocked. Each test states one promise
of the step it covers: gaps creates coins and not products and never a second
record for a coin we already have, repair-gaps fills what an earlier run left
empty and touches nothing else, merge moves every coin of every owner before
the old record goes, titles takes the issuer's wording, photos falls back from
the National Bank to ua-coins and never downloads the same image twice, prices
flags what fails the checks.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Denomination,
    MarketPriceSnapshot,
    MediaFile,
    PriceSourceLink,
)
from app.models.enums import (
    CollectionGroup,
    MediaRole,
    MediaSource,
    MetalKind,
    TranslationSource,
)
from app.ukraine_pipeline import bridge, gaps, merge, photos, prices, repair, series, titles
from app.ukraine_pipeline.catalog import load_items, ukraine_country_id
from app.ukraine_pipeline.lexicon import load_lexicon
from app.ukraine_pipeline.report import PipelineReport
from app.ukraine_pipeline.sources import NbuEnglish, Sources, roll_coin
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SourceRecord
from app.ukraine_recon.triangulate import Cluster, cluster_records
from tests.seed import (
    add_collection_item,
    country_by_code,
    make_catalog_item,
    make_user,
    seed_currencies,
    seed_reference,
)

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
    extra: dict[str, object] | None = None,
) -> SourceRecord:
    """A card as the National Bank really writes one: "2 грн", "срібло"."""
    return SourceRecord(
        source=SOURCE_NBU,
        source_id=source_id,
        title_uk=title,
        denomination=Decimal(denomination),
        denomination_label=f"{denomination} грн",
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
            **(extra or {}),
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


# ------------------------------------------------------ gaps: the whole record
async def test_gaps_fills_the_face_value_the_metal_and_the_series(
    db_session: AsyncSession,
) -> None:
    """A record made from a card is a record, not a name and a year.

    The card writes "1 грн" and "срібло"; a face value the parser cannot read
    and a metal it does not recognise are what left 96 records empty.
    """
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    found = sources_of(
        nbu_record(
            "1767",
            title='"До 30-річчя грошової реформи в Україні" (c)',
            year=2026,
            denomination="1",
            series_name="Українська держава",
            material="срібло",
            extra={"massGrams": "31.1", "diameterMm": "38.6", "edge": "рифлений"},
        ),
        english={"1767": NbuEnglish(title="30 Years of the Currency Reform", series="Ukraine")},
    )

    outcome = await gaps.create_missing(
        db_session, country_id=country.id, sources=found, linked_keys=set(), dry_run=False
    )
    await db_session.commit()

    assert outcome.summary()["created"] == 1
    created = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.source_key == "nbu:1767"))
    ).scalar_one()
    assert created.title_original == "До 30-річчя грошової реформи в Україні"
    assert created.denomination_id is not None
    denomination = await db_session.get(Denomination, created.denomination_id)
    assert denomination is not None
    assert (denomination.value, denomination.unit) == (Decimal("1.000"), "hryvnia")
    # Silver carries no fineness on the card, so there is no dictionary row —
    # but the metal kind is known, and that is what the collection value uses.
    assert created.metal_kind is MetalKind.PRECIOUS
    assert created.composition_id is None
    assert created.material == "срібло"
    assert created.weight_grams == Decimal("31.100")
    assert created.diameter_mm == Decimal("38.60")
    assert created.edge == "рифлений"
    series = await db_session.get(CoinSeries, created.series_id)
    assert series is not None
    assert series.name_original == "Українська держава"


async def test_gaps_creates_nothing_from_a_roll_card(db_session: AsyncSession) -> None:
    """A roll card names the coin well enough to match it, not to create it."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    coin = roll_coin(
        SourceRecord(
            source=SOURCE_NBU,
            source_id="1740",
            title_uk=(
                'Ролик обігових пам`ятних монет "Ми сильні. Ми разом. Запорізька область" '
                "(у ролику 25 монет)"
            ),
            denomination=Decimal(250),
            denomination_label="250 грн",
            year=2026,
            kind="souvenir",
            url="https://bank.gov.ua/",
        )
    )
    assert coin is not None
    found = sources_of(coin)

    outcome = await gaps.create_missing(
        db_session, country_id=country.id, sources=found, linked_keys=set(), dry_run=False
    )
    assert outcome.summary() == {
        **outcome.summary(),
        "created": 0,
        "skippedRollOnly": 1,
    }
    assert (await db_session.execute(select(CatalogItem))).scalars().all() == []


async def test_gaps_does_not_duplicate_one_of_our_unlinked_records(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """The defect: four "Пектораль" of ours met four new ones from the cards.

    Same year, same face value, nothing linked: the coin is almost certainly
    one we already have, so the pair goes into a file instead of the database.
    """
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    hryvnia = Denomination(
        country_id=country.id,
        currency_code="UAH",
        value=Decimal(20),
        unit="hryvnia",
        sort_order=2000,
    )
    db_session.add(hryvnia)
    await db_session.flush()
    ours = await make_catalog_item(
        db_session,
        country=country,
        title="Пектораль",
        year=2021,
        denomination=hryvnia,
    )
    found = sources_of(
        nbu_record("1307", title="Пектораль", year=2021, denomination="20", series_name=None)
    )
    items = await load_items(db_session, country.id)

    outcome = await gaps.create_missing(
        db_session,
        country_id=country.id,
        sources=found,
        linked_keys=set(),
        dry_run=False,
        items=items,
        linked_ids=set(),
    )
    await db_session.commit()

    assert outcome.summary()["created"] == 0
    assert outcome.summary()["wouldDuplicate"] == 1
    row = outcome.would_duplicate[0]
    assert (row["itemId"], row["clusterKey"], row["note"]) == (
        ours.id,
        "nbu:1307",
        "would_duplicate",
    )

    # The file it writes is the one --apply-review already reads.
    path = tmp_path / "duplicates.csv"
    assert gaps.write_duplicates_csv(path, outcome) == 1
    text = path.read_text(encoding="utf-8").replace("\n,", "\nyes,")
    path.write_text(text, encoding="utf-8")
    assert bridge.read_review_csv(path) == {ours.id: "nbu:1307"}


async def test_a_record_already_linked_does_not_hold_a_coin_back(
    db_session: AsyncSession,
) -> None:
    """The guard only counts records nothing points at."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    ours = await make_catalog_item(db_session, country=country, title="Пектораль", year=2021)
    found = sources_of(nbu_record("1307", title="Інша монета", year=2021, denomination="20"))
    items = await load_items(db_session, country.id)

    outcome = await gaps.create_missing(
        db_session,
        country_id=country.id,
        sources=found,
        linked_keys=set(),
        dry_run=False,
        items=items,
        linked_ids={ours.id},
    )
    assert outcome.summary()["created"] == 1


# --------------------------------------------------------------- repair-gaps
async def test_repair_fills_the_columns_an_earlier_run_left_empty(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    # A record as the first version of the gaps step wrote it: a name, a year,
    # a source key and nothing else.
    empty = await make_catalog_item(
        db_session,
        country=country,
        title="До 30-річчя грошової реформи в Україні",
        year=2026,
        source_key="nbu:1767",
    )
    found = sources_of(
        nbu_record(
            "1767",
            title="До 30-річчя грошової реформи в Україні",
            year=2026,
            denomination="1",
            series_name="Українська держава",
            material="срібло",
            extra={"massGrams": "31.1"},
        ),
        english={"1767": NbuEnglish(title="30 Years of the Currency Reform", series="Ukraine")},
    )

    outcome = await repair.repair_gaps(
        db_session, country_id=country.id, sources=found, dry_run=False
    )
    await db_session.commit()

    assert outcome.summary()["updated"] == 1
    assert outcome.filled["denomination_id"] == 1
    assert outcome.filled["metal_kind"] == 1
    assert outcome.filled["series_id"] == 1
    stored = await db_session.get(CatalogItem, empty.id)
    assert stored is not None
    assert stored.denomination_id is not None
    assert stored.metal_kind is MetalKind.PRECIOUS
    assert stored.series_id is not None
    assert stored.title_en == "30 Years of the Currency Reform"
    assert stored.weight_grams == Decimal("31.100")

    # Run twice: the second pass has nothing left to fill.
    again = await repair.repair_gaps(
        db_session, country_id=country.id, sources=found, dry_run=False
    )
    assert (again.updated, again.unchanged) == (0, 1)


async def test_repair_never_overwrites_what_is_already_there(
    db_session: AsyncSession,
) -> None:
    """A correction a person made outranks the card."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    corrected = await make_catalog_item(
        db_session,
        country=country,
        title="Соня садова",
        year=1999,
        source_key="nbu:1",
        metal_kind=MetalKind.BASE,
        edge="гладкий",
    )
    found = sources_of(nbu_record("1", material="срібло", extra={"edge": "рифлений"}))

    await repair.repair_gaps(db_session, country_id=country.id, sources=found, dry_run=False)
    await db_session.commit()

    stored = await db_session.get(CatalogItem, corrected.id)
    assert stored is not None
    assert stored.metal_kind is MetalKind.BASE
    assert stored.edge == "гладкий"


# --------------------------------------------------------------------- merge
async def test_merge_lists_the_pairs_with_the_card_prose_beside_them(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    await make_catalog_item(
        db_session, country=country, title="Пектораль (лев)", year=2021, source_key=None
    )
    await make_catalog_item(
        db_session, country=country, title="Пектораль", year=2021, source_key="nbu:1307"
    )
    found = sources_of(
        nbu_record(
            "1307",
            title="Пектораль",
            year=2021,
            denomination="20",
            extra={"description": ["На реверсі зображено пектораль із фігурою лева."]},
        )
    )

    outcome = await merge.find_pairs(
        db_session, country_id=country.id, sources=found, lexicon=LEXICON
    )
    assert len(outcome.candidates) == 1
    row = outcome.candidates[0]
    assert row["gapSourceKey"] == "nbu:1307"
    assert "лева" in row["nbuDescription"]
    assert "лев" in row["sharedWords"]


async def test_merge_dry_run_report_survives_a_candidate_with_a_face_value(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """A candidate's denomination is a Decimal — report.write must not choke on it."""
    ref = await seed_reference(db_session)
    await make_catalog_item(
        db_session, country=ref.ukraine, title="Пектораль (лев)", year=2021, source_key=None
    )
    await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Пектораль",
        year=2021,
        source_key="nbu:1307",
        denomination=ref.uah_2,
    )
    found = sources_of(nbu_record("1307", title="Пектораль", year=2021, denomination="2"))
    outcome = await merge.find_pairs(
        db_session, country_id=ref.ukraine.id, sources=found, lexicon=LEXICON
    )
    assert isinstance(outcome.candidates[0]["denomination"], Decimal)

    report = PipelineReport()
    report.step("merge", outcome.summary(), candidates=outcome.candidates)
    path = tmp_path / "report.json"

    report.write(path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["details"]["merge"]["candidates"][0]["denomination"] == "2.000"


async def test_merge_moves_the_owners_coins_and_retires_the_old_record(
    db_session: AsyncSession,
) -> None:
    """The point of the step: nothing of the owner's is lost, one record is left."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    owner = await make_user(db_session, email="owner@example.test")
    old = await make_catalog_item(db_session, country=country, title="Пектораль", year=2021)
    kept = await make_catalog_item(
        db_session, country=country, title="Пектораль", year=2021, source_key="nbu:1307"
    )
    await add_collection_item(
        db_session, owner_id=owner.id, item=old, quantity=2, price="500", rate_uah="1"
    )
    await add_collection_item(
        db_session, owner_id=owner.id, item=old, quantity=1, price="300", rate_uah="1"
    )
    db_session.add(
        MediaFile(
            catalog_item_id=old.id,
            owner_id=owner.id,
            role=MediaRole.OBVERSE,
            source=MediaSource.USER_UPLOAD,
            storage_key="catalog/old/obverse.webp",
        )
    )
    await db_session.commit()

    before_old = await merge.holdings_of(db_session, old.id)
    assert (before_old.instances, before_old.quantity, before_old.media) == (2, 3, 1)
    assert before_old.purchase_uah == Decimal("1300.00")

    outcome = await merge.apply_merges(db_session, [(kept.id, old.id)], dry_run=False)
    await db_session.commit()

    assert outcome.problems == []
    row = outcome.merged[0]
    assert row["deleted"] is True
    assert row["after"] == {
        "instances": 2,
        "quantity": 3,
        "purchaseUah": "1300.00",
        "media": 1,
    }
    assert await db_session.get(CatalogItem, old.id) is None
    moved = (
        (
            await db_session.execute(
                select(CollectionItem).where(CollectionItem.catalog_item_id == kept.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(moved) == 2
    photo = (
        await db_session.execute(select(MediaFile).where(MediaFile.catalog_item_id == kept.id))
    ).scalar_one()
    assert photo.storage_key == "catalog/old/obverse.webp"


async def test_a_dry_run_merges_nothing(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    owner = await make_user(db_session, email="dry@example.test")
    old = await make_catalog_item(db_session, country=country, title="Пектораль", year=2021)
    kept = await make_catalog_item(
        db_session, country=country, title="Пектораль", year=2021, source_key="nbu:1307"
    )
    await add_collection_item(db_session, owner_id=owner.id, item=old, quantity=2, price="500")

    outcome = await merge.apply_merges(db_session, [(kept.id, old.id)], dry_run=True)
    await db_session.commit()

    assert outcome.merged[0]["deleted"] is False
    assert outcome.merged[0]["after"]["quantity"] == 2
    assert await db_session.get(CatalogItem, old.id) is not None
    assert (await merge.holdings_of(db_session, kept.id)).instances == 0


async def test_a_personal_item_is_never_merged(db_session: AsyncSession) -> None:
    """The pipeline speaks for the issuer; a personal item belongs to its author."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    owner = await make_user(db_session, email="author@example.test")
    personal = await make_catalog_item(
        db_session, country=country, title="Моя монета", year=2021, created_by=owner.id
    )
    kept = await make_catalog_item(
        db_session, country=country, title="Пектораль", year=2021, source_key="nbu:1307"
    )

    outcome = await merge.apply_merges(db_session, [(kept.id, personal.id)], dry_run=False)
    assert outcome.merged == []
    assert outcome.problems and "shared records" in outcome.problems[0]
    assert await db_session.get(CatalogItem, personal.id) is not None


async def test_a_merge_file_naming_one_record_twice_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "merge.csv"
    path.write_text(
        "decision,gapItemId,ourItemId\nyes,3106,1122\nyes,3107,1122\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="twice"):
        merge.read_merge_csv(path)


def test_a_merge_file_reads_back_with_an_excel_bom(tmp_path: Path) -> None:
    path = tmp_path / "merge.csv"
    path.write_bytes(
        "decision,gapItemId,ourItemId\nyes,3106,1122\n,3107,1123\n".encode("utf-8-sig")
    )
    assert merge.read_merge_csv(path) == [(3106, 1122)]
