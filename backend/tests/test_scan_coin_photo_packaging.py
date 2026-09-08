"""scan_coin_photo_packaging: candidate selection, classification, the CSV
review round-trip, and the ua-coins replacement flow.

Photo bytes are synthetic (the same circle/rectangle drawing
tests/test_classify_coin_photos.py uses) — no real catalog photo is
committed to the repository (CLAUDE.md).
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, MediaFile
from app.models.enums import MediaRole, MediaSource
from app.ukraine_recon.http import PoliteClient
from scripts import scan_coin_photo_packaging as scan_script
from tests.seed import country_by_code, make_catalog_item, seed_currencies

BACKGROUND = (245, 245, 245)
COIN_COLOR = (150, 120, 70)


class RecordingStorage:
    """Stands in for MinIO: an in-memory dict, same shape ObjectStorage offers."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self.objects[key] = payload

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete_many(self, keys: list[str]) -> None:
        for key in keys:
            self.objects.pop(key, None)

    def ensure_bucket(self) -> None:
        return None


def _png_bytes(*, coin: bool) -> bytes:
    image = Image.new("RGB", (300, 300), BACKGROUND)
    draw = ImageDraw.Draw(image)
    if coin:
        draw.ellipse((40, 40, 260, 260), fill=COIN_COLOR)
    else:
        draw.rectangle((100, 20, 200, 280), fill=COIN_COLOR)  # an upright tube
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _add_photo(
    session: AsyncSession,
    *,
    item: CatalogItem,
    role: MediaRole,
    key: str,
    storage: RecordingStorage,
    coin: bool,
) -> None:
    storage.put(key, _png_bytes(coin=coin), "image/png")
    session.add(
        MediaFile(
            catalog_item_id=item.id,
            role=role,
            source=MediaSource.NBU,
            storage_key=key,
            variants={"600": key},
        )
    )
    await session.commit()


@pytest.fixture
def mock_client(tmp_path: Path) -> PoliteClient:
    listing_html = (
        Path(__file__).parent / "fixtures" / "ukraine_recon" / "ua_coins_regular_ua_listing.html"
    ).read_text(encoding="utf-8")
    detail_html = (
        Path(__file__).parent / "fixtures" / "ukraine_recon" / "ua_coins_regular_ua_detail.html"
    ).read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/ua/regular-ua/"):
            return httpx.Response(200, text=listing_html)
        if "/show-regular-ua/" in url:
            return httpx.Response(200, text=detail_html)
        if url.endswith(".webp"):
            return httpx.Response(200, content=_png_bytes(coin=True))
        return httpx.Response(404)

    return PoliteClient(
        cache_dir=tmp_path / "cache", transport=httpx.MockTransport(handler), sleep=lambda _s: None
    )


async def test_candidate_items_includes_my_sylni_even_without_a_photo(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    without_photo = await make_catalog_item(
        db_session, country=country, title="Ми сильні. Ми разом. Запорізька область", year=2026
    )
    unrelated = await make_catalog_item(db_session, country=country, title="Соня садова", year=1999)

    items = await scan_script._candidate_items(db_session, country_id=country.id)

    ids = {item.id for item in items}
    assert without_photo.id in ids
    assert unrelated.id not in ids


async def test_scan_flags_a_packaging_photo_and_leaves_a_coin_photo_alone(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    storage = RecordingStorage()
    packaging_item = await make_catalog_item(
        db_session, country=country, title="Ми сильні. Ми разом. Одеська область", year=2022
    )
    await _add_photo(
        db_session,
        item=packaging_item,
        role=MediaRole.OBVERSE,
        key="a",
        storage=storage,
        coin=False,
    )
    coin_item = await make_catalog_item(db_session, country=country, title="Соня садова", year=1999)
    await _add_photo(
        db_session, item=coin_item, role=MediaRole.OBVERSE, key="b", storage=storage, coin=True
    )

    outcome = await scan_script.scan(
        db_session, storage=storage, country_id=country.id, limit=None, log=lambda _m: None
    )

    by_id = {item.item_id: item for item in outcome.items}
    assert by_id[packaging_item.id].is_coin is False
    assert by_id[coin_item.id].is_coin is True


def test_csv_round_trips_the_replacement_decision(tmp_path: Path) -> None:
    outcome = scan_script.ScanOutcome(
        items=[
            scan_script.ItemVerdict(
                item_id=7,
                title="Ми сильні. Ми разом. Одеська область",
                year=2022,
                is_coin=False,
                worst_circularity=0.3,
                worst_aspect=0.2,
                worst_fill=0.4,
                note="non-circular object in a stored photo",
            )
        ]
    )
    path = tmp_path / "review.csv"
    rows = scan_script.write_report_csv(path, outcome, {7: "https://www.ua-coins.info/x"})
    assert rows == 1

    text = path.read_text(encoding="utf-8")
    text = text.replace("\n,7,", "\nyes,7,", 1)
    path.write_text(text, encoding="utf-8")

    decisions = scan_script.read_review_csv(path)
    assert decisions == {7: "https://www.ua-coins.info/x"}


def test_find_replacements_matches_the_real_listing_fixture(mock_client: PoliteClient) -> None:
    class Item:
        def __init__(self, item_id: int, title: str) -> None:
            self.id = item_id
            self.title_original = title

    items = [Item(1, "Ми сильні. Ми разом. Запорізька область"), Item(2, "Соня садова")]
    with mock_client as client:
        found = scan_script.find_replacements(client, items)
    assert 2 not in found
    assert found[1].endswith("zaporizka-oblast")


async def test_apply_replacements_removes_the_old_photo_and_stores_the_new_one(
    db_session: AsyncSession, mock_client: PoliteClient
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    storage = RecordingStorage()
    item = await make_catalog_item(
        db_session, country=country, title="Ми сильні. Ми разом. Запорізька область", year=2026
    )
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.OBVERSE,
        key="old-obverse",
        storage=storage,
        coin=False,
    )

    with mock_client as client:
        outcome = await scan_script.apply_replacements(
            db_session,
            storage=storage,
            client=client,
            decisions={item.id: "https://www.ua-coins.info/ua/show-regular-ua/280-x"},
            dry_run=False,
            log=lambda _m: None,
        )

    assert outcome.summary()["replaced"] == 1
    assert outcome.summary()["failed"] == 0
    assert "old-obverse" not in storage.objects

    rows = (
        (await db_session.execute(select(MediaFile).where(MediaFile.catalog_item_id == item.id)))
        .scalars()
        .all()
    )
    assert {row.source for row in rows} == {MediaSource.UA_COINS}
    assert {str(row.role) for row in rows} == {"obverse", "reverse"}
