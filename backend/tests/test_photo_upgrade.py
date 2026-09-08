"""photo_upgrade: the three-tier obverse/reverse pick, the confident-win
threshold, and the end-to-end scan/apply/idempotency round trip.

Photo bytes are synthetic (Pillow-drawn circles and rectangles, the same
approach tests/test_classify_coin_photos.py and
tests/test_scan_coin_photo_packaging.py use) — no real catalog photo is
committed to the repository (CLAUDE.md).
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, MediaFile, PriceSourceLink
from app.models.enums import MatchStatus, MediaRole, MediaSource
from app.ukraine_pipeline import photo_upgrade
from app.ukraine_pipeline.catalog import LINK_SOURCES
from app.ukraine_pipeline.classify_coin_photos import Verdict
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCE_UA_COINS
from app.ukraine_recon.ua_coins import GalleryImage
from tests.seed import country_by_code, make_catalog_item, seed_currencies

BACKGROUND = (245, 245, 245)
COIN_COLOR = (150, 120, 70)


def _bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def coin_bytes(*, size: int = 300, diameter: int = 220) -> bytes:
    image = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    margin = (size - diameter) // 2
    draw.ellipse((margin, margin, margin + diameter, margin + diameter), fill=COIN_COLOR)
    return _bytes(image)


def packaging_bytes(*, size: int = 300) -> bytes:
    """An upright tube: fails the aspect check, same as the roll-card photos."""
    image = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((size * 0.35, size * 0.1, size * 0.65, size * 0.9), fill=COIN_COLOR)
    return _bytes(image)


def figural_bytes(*, size: int = 300) -> bytes:
    """A stand-in for a genuinely non-circular coin (Писанка, Пектораль):
    same low-circularity shape whichever page it is read off, so a
    photo-upgrade candidate can never confidently beat it either."""
    image = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.ellipse((size * 0.25, size * 0.05, size * 0.75, size * 0.95), fill=COIN_COLOR)
    draw.polygon(
        [(size * 0.5, size * 0.02), (size * 0.7, size * 0.2), (size * 0.3, size * 0.2)],
        fill=COIN_COLOR,
    )
    return _bytes(image)


class RecordingStorage:
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


def routed_client(tmp_path: Path, routes: dict[str, str | bytes]) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = routes.get(str(request.url))
        if payload is None:
            return httpx.Response(404)
        if isinstance(payload, str):
            return httpx.Response(200, text=payload)
        return httpx.Response(200, content=payload)

    return PoliteClient(
        cache_dir=tmp_path / "cache", transport=httpx.MockTransport(handler), sleep=lambda _s: None
    )


async def _add_photo(
    session: AsyncSession,
    *,
    item: CatalogItem,
    role: MediaRole,
    key: str,
    storage: RecordingStorage,
    payload: bytes,
    source: MediaSource = MediaSource.NBU,
) -> None:
    storage.put(key, payload, "image/png")
    session.add(
        MediaFile(
            catalog_item_id=item.id,
            role=role,
            source=source,
            storage_key=key,
            variants={"600": key},
        )
    )
    await session.commit()


async def _link_ua_coins(session: AsyncSession, *, item: CatalogItem, url: str) -> None:
    session.add(
        PriceSourceLink(
            catalog_item_id=item.id,
            source=LINK_SOURCES[SOURCE_UA_COINS],
            external_id=url,
            match_status=MatchStatus.CONFIRMED,
        )
    )
    await session.commit()


def gallery_html(images: list[tuple[str, str]]) -> str:
    """A minimal fancybox gallery: (absolute url, alt) pairs, in order."""
    parts = [
        f'<a href="{url}" data-fancybox="gallery"><img src="{url}" alt="{alt}"/></a>'
        for url, alt in images
    ]
    return "<div>" + "".join(parts) + "</div>"


PAGE_URL = "https://www.ua-coins.info/ua/list/999-test-coin"
OBVERSE_URL = "https://www.ua-coins.info/images/coins/big/999_obverse.webp"
REVERSE_URL = "https://www.ua-coins.info/images/coins/big/999_reverse.webp"


# --------------------------------------------------------- pure: role picking
def test_metadata_tier_wins_over_geometry_when_both_could_resolve_a_role() -> None:
    obverse_meta = GalleryImage(
        url="https://x/1", alt="Аверс 5 гривень", filename="1.webp", order=0
    )
    reverse_meta = GalleryImage(
        url="https://x/2", alt="Реверс 5 гривень", filename="2.webp", order=1
    )
    picks = photo_upgrade.pick_roles_by_metadata([obverse_meta, reverse_meta])
    assert picks["obverse"].image is obverse_meta
    assert picks["obverse"].tier == "metadata"
    assert picks["reverse"].image is reverse_meta


def test_metadata_reads_the_filename_when_alt_is_empty() -> None:
    image = GalleryImage(url="https://x/1", alt="", filename="999_obverse.webp", order=0)
    picks = photo_upgrade.pick_roles_by_metadata([image])
    assert picks["obverse"].image is image


def test_geometry_tier_fills_a_role_metadata_left_unresolved() -> None:
    """Two anonymous gallery images, one clearly coin-shaped: geometry ranks
    it first for the one role tier 1 could not name."""
    coin = GalleryImage(url="https://x/coin", alt="", filename="a.jpg", order=0)
    packaging = GalleryImage(url="https://x/pack", alt="", filename="b.jpg", order=1)
    verdicts = {
        "https://x/coin": Verdict(True, 1, 0.95, 0.95, 0.95, "ok"),
        "https://x/pack": Verdict(False, 1, 0.10, 0.20, 0.10, "non-circular object in frame"),
    }
    picks = photo_upgrade.pick_roles([coin, packaging], verdicts)
    assert picks["obverse"].image is coin
    assert picks["obverse"].tier == "geometry"
    assert picks["reverse"].image is packaging  # only one left, still assigned


def test_geometry_tier_never_reassigns_a_metadata_claimed_image() -> None:
    obverse_meta = GalleryImage(url="https://x/1", alt="Аверс", filename="1.jpg", order=0)
    unlabeled = GalleryImage(url="https://x/2", alt="", filename="2.jpg", order=1)
    verdicts = {"https://x/2": Verdict(True, 1, 0.9, 0.9, 0.9, "ok")}
    picks = photo_upgrade.pick_roles([obverse_meta, unlabeled], verdicts)
    assert picks["obverse"].image is obverse_meta
    assert picks["obverse"].tier == "metadata"
    assert picks["reverse"].image is unlabeled
    assert picks["reverse"].tier == "geometry"


def test_tier_three_leaves_a_role_unresolved_when_nothing_is_left() -> None:
    obverse_meta = GalleryImage(url="https://x/1", alt="Аверс", filename="1.jpg", order=0)
    picks = photo_upgrade.pick_roles([obverse_meta], {})
    assert "obverse" in picks
    assert "reverse" not in picks


# ------------------------------------------------------------ pure: threshold
def test_should_replace_on_a_clearly_good_candidate_and_bad_current() -> None:
    assert photo_upgrade.should_replace(current_score=0.65, candidate_score=0.85) is True


def test_should_not_replace_a_decent_current_photo_for_a_marginal_gain() -> None:
    assert photo_upgrade.should_replace(current_score=0.66, candidate_score=0.85) is False


def test_should_replace_on_a_wide_enough_gap_even_below_the_top_threshold() -> None:
    assert photo_upgrade.should_replace(current_score=0.40, candidate_score=0.70) is True


def test_should_not_replace_two_similarly_bad_photos() -> None:
    """A wide relative gap between two poor scores is not a confident win —
    this is what protects a figural coin whose own gallery is just as
    non-circular as what is already stored."""
    assert photo_upgrade.should_replace(current_score=0.10, candidate_score=0.36) is False


def test_should_not_replace_when_current_is_already_as_good() -> None:
    assert photo_upgrade.should_replace(current_score=0.85, candidate_score=0.85) is False


# --------------------------------------------------------------- duplicates
def test_find_duplicate_titles_groups_by_title_and_year() -> None:
    items = [
        CatalogItem(id=1, title_original="Український борщ", issue_year=2022),
        CatalogItem(id=2, title_original="Український борщ", issue_year=2022),
        CatalogItem(id=3, title_original="Соня садова", issue_year=1999),
    ]
    duplicates = photo_upgrade.find_duplicate_titles(items)
    assert duplicates == [
        {"titleOriginal": "Український борщ", "issueYear": 2022, "itemIds": [1, 2]}
    ]


# -------------------------------------------------------------------- async
async def test_candidate_items_only_counts_rows_with_an_absolute_ua_coins_url(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    with_url = await make_catalog_item(db_session, country=country, title="A", year=2020)
    await _link_ua_coins(db_session, item=with_url, url="https://www.ua-coins.info/ua/list/1-a")
    bare_id = await make_catalog_item(db_session, country=country, title="B", year=2020)
    db_session.add(
        PriceSourceLink(
            catalog_item_id=bare_id.id,
            source=LINK_SOURCES[SOURCE_UA_COINS],
            external_id="1234",
            match_status=MatchStatus.CONFIRMED,
        )
    )
    await db_session.commit()
    without_link = await make_catalog_item(db_session, country=country, title="C", year=2020)

    rows = await photo_upgrade.candidate_items(db_session, country_id=country.id)

    ids = {item.id for item, _url in rows}
    assert with_url.id in ids
    assert bare_id.id not in ids
    assert without_link.id not in ids


async def test_scan_proposes_a_confident_metadata_replacement(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    storage = RecordingStorage()
    item = await make_catalog_item(db_session, country=country, title="Test coin", year=2022)
    await _link_ua_coins(db_session, item=item, url=PAGE_URL)
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.OBVERSE,
        key="old-o",
        storage=storage,
        payload=packaging_bytes(),
    )
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.REVERSE,
        key="old-r",
        storage=storage,
        payload=packaging_bytes(),
    )
    html = gallery_html([(OBVERSE_URL, "Аверс"), (REVERSE_URL, "Реверс")])
    client = routed_client(
        tmp_path,
        {PAGE_URL: html, OBVERSE_URL: coin_bytes(), REVERSE_URL: coin_bytes()},
    )

    with client:
        outcome = await photo_upgrade.scan(
            db_session,
            storage=storage,
            client=client,
            country_id=country.id,
            limit=None,
            log=lambda _m: None,
        )

    assert outcome.scanned == 1
    assert len(outcome.diffs) == 1
    diff = outcome.diffs[0]
    assert diff.item_id == item.id
    assert diff.tier == "metadata"
    assert diff.obverse_url == OBVERSE_URL
    assert diff.reverse_url == REVERSE_URL
    assert diff.candidate_score > diff.current_score


async def test_figural_coin_is_never_a_confident_win(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    storage = RecordingStorage()
    item = await make_catalog_item(db_session, country=country, title="Писанка", year=2022)
    await _link_ua_coins(db_session, item=item, url=PAGE_URL)
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.OBVERSE,
        key="old-o",
        storage=storage,
        payload=figural_bytes(),
    )
    html = gallery_html([(OBVERSE_URL, "Аверс")])
    client = routed_client(tmp_path, {PAGE_URL: html, OBVERSE_URL: figural_bytes()})

    with client:
        outcome = await photo_upgrade.scan(
            db_session,
            storage=storage,
            client=client,
            country_id=country.id,
            limit=None,
            log=lambda _m: None,
        )

    assert outcome.diffs == []
    assert outcome.fallbacks == []


async def test_missing_role_candidate_is_reported_as_a_fallback_not_a_diff(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    storage = RecordingStorage()
    item = await make_catalog_item(db_session, country=country, title="Test coin", year=2022)
    await _link_ua_coins(db_session, item=item, url=PAGE_URL)
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.OBVERSE,
        key="old-o",
        storage=storage,
        payload=packaging_bytes(),
    )
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.REVERSE,
        key="old-r",
        storage=storage,
        payload=packaging_bytes(),
    )
    # Only one gallery image at all — nothing left to resolve "reverse" with.
    html = gallery_html([(OBVERSE_URL, "Аверс")])
    client = routed_client(tmp_path, {PAGE_URL: html, OBVERSE_URL: coin_bytes()})

    with client:
        outcome = await photo_upgrade.scan(
            db_session,
            storage=storage,
            client=client,
            country_id=country.id,
            limit=None,
            log=lambda _m: None,
        )

    assert outcome.diffs == []
    assert len(outcome.fallbacks) == 1
    assert outcome.fallbacks[0]["itemId"] == item.id
    assert "reverse" in cast_reason(outcome.fallbacks[0])


def cast_reason(row: dict[str, object]) -> str:
    return str(row["reason"])


async def test_apply_then_rescan_gives_an_empty_diff(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    storage = RecordingStorage()
    item = await make_catalog_item(db_session, country=country, title="Test coin", year=2022)
    await _link_ua_coins(db_session, item=item, url=PAGE_URL)
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.OBVERSE,
        key="old-o",
        storage=storage,
        payload=packaging_bytes(),
    )
    await _add_photo(
        db_session,
        item=item,
        role=MediaRole.REVERSE,
        key="old-r",
        storage=storage,
        payload=packaging_bytes(),
    )
    html = gallery_html([(OBVERSE_URL, "Аверс"), (REVERSE_URL, "Реверс")])
    client = routed_client(
        tmp_path, {PAGE_URL: html, OBVERSE_URL: coin_bytes(), REVERSE_URL: coin_bytes()}
    )

    with client:
        first = await photo_upgrade.scan(
            db_session,
            storage=storage,
            client=client,
            country_id=country.id,
            limit=None,
            log=lambda _m: None,
        )
        assert len(first.diffs) == 1
        apply_outcome = await photo_upgrade.apply_diffs(
            db_session,
            storage=storage,
            client=client,
            diffs=first.diffs,
            only_item_ids=None,
            log=lambda _m: None,
        )
        assert apply_outcome.summary()["replaced"] == 1

        second = await photo_upgrade.scan(
            db_session,
            storage=storage,
            client=client,
            country_id=country.id,
            limit=None,
            log=lambda _m: None,
        )

    assert second.diffs == []
    rows = (
        (await db_session.execute(select(MediaFile).where(MediaFile.catalog_item_id == item.id)))
        .scalars()
        .all()
    )
    assert {row.source for row in rows} == {MediaSource.UA_COINS}


def test_diff_csv_round_trips_the_decision_column(tmp_path: Path) -> None:
    outcome = photo_upgrade.PhotoUpgradeOutcome(
        diffs=[
            photo_upgrade.ItemDiff(
                item_id=42,
                title="Test coin",
                year=2022,
                current_score=0.3,
                candidate_score=0.9,
                tier="metadata",
                obverse_url=OBVERSE_URL,
                reverse_url=REVERSE_URL,
            )
        ]
    )
    path = tmp_path / "diff.csv"
    rows = photo_upgrade.write_diff_csv(path, outcome)
    assert rows == 1

    text = path.read_text(encoding="utf-8")
    text = text.replace("\n,42,", "\nyes,42,", 1)
    path.write_text(text, encoding="utf-8")

    assert photo_upgrade.read_review_csv(path) == {42}
