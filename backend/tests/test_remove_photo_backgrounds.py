"""scripts/remove_photo_backgrounds.py against the real schema.

The script has no package home (like every other one-off in scripts/), so it
is loaded by path the same way `python scripts/remove_photo_backgrounds.py`
would run it; app.services.media_background's own classification rules are
covered separately in tests/test_media_background.py, so a plain white circle
is enough here to reach the "cut" branch.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaFile
from app.models.enums import MediaRole, MediaSource
from tests.seed import make_catalog_item, seed_reference

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "remove_photo_backgrounds.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("remove_photo_backgrounds", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rpb() -> ModuleType:
    return _load_script()


class FakeStorage:
    """Stands in for MinIO: an in-memory dict, keyed like the real bucket."""

    def __init__(self, seed: dict[str, bytes] | None = None) -> None:
        self.objects: dict[str, bytes] = dict(seed or {})

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self.objects[key] = payload


def _round_coin_jpeg(side: int = 600) -> bytes:
    img = Image.new("RGB", (side, side), (255, 255, 255))
    margin = side // 6
    ImageDraw.Draw(img).ellipse((margin, margin, side - margin, side - margin), fill=(150, 120, 40))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _square_blister_jpeg(side: int = 600) -> bytes:
    img = Image.new("RGB", (side, side), (255, 255, 255))
    margin = side // 6
    box = (margin, margin, side - margin, side - margin)
    ImageDraw.Draw(img).rectangle(box, fill=(80, 80, 200))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _nobg_round_coin_webp(side: int = 600, coin_fraction: float = 0.3) -> bytes:
    """An already-cut object: wide transparent margins around an opaque disc."""
    img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    margin = round(side * (1 - coin_fraction) / 2)
    ImageDraw.Draw(img).ellipse(
        (margin, margin, side - margin, side - margin), fill=(150, 120, 40, 255)
    )
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", lossless=True)
    return buffer.getvalue()


async def _make_media(
    session: AsyncSession,
    *,
    catalog_item_id: int,
    storage_key: str | None,
    external_url: str | None = None,
    variants: dict[str, str] | None = None,
) -> MediaFile:
    media = MediaFile(
        catalog_item_id=catalog_item_id,
        role=MediaRole.OBVERSE,
        source=MediaSource.NBU,
        storage_key=storage_key,
        external_url=external_url,
        variants=variants,
        mime_type="image/webp" if storage_key else None,
    )
    session.add(media)
    await session.commit()
    session.expunge(media)
    return media


async def test_find_candidates_skips_hotlinks_and_already_processed(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Test coin", year=2020
    )
    eligible = await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key="catalog/1/obverse/aaa_1200.webp",
        variants={"1200": "catalog/1/obverse/aaa_1200.webp"},
    )
    await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=None,
        external_url="https://i.ucoin.net/x.jpg",
    )
    await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key="catalog/1/obverse/bbb-nobg_1200.webp",
        variants={"1200": "catalog/1/obverse/bbb-nobg_1200.webp"},
    )

    candidates, already_processed = await rpb.find_candidates(db_session, only_ids=None)

    assert already_processed == 1
    assert [c.media_id for c in candidates] == [eligible.id]
    assert candidates[0].title == "Test coin"
    assert candidates[0].source_key == "catalog/1/obverse/aaa_1200.webp"


async def test_dry_run_classifies_without_touching_storage_or_db(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Dry run coin", year=2021
    )
    key = "catalog/2/obverse/ccc_600.webp"
    media = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key}
    )
    storage = FakeStorage({key: _round_coin_jpeg()})

    candidates, _ = await rpb.find_candidates(db_session, only_ids=None)
    outcome = await rpb.process_candidates(
        db_session, storage, candidates, apply=False, log=lambda _: None
    )

    assert outcome.cut == 1
    assert outcome.applied == 0
    assert set(storage.objects) == {key}  # nothing new written

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == key  # untouched


async def test_apply_writes_nobg_object_and_keeps_the_original(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Apply coin", year=2022
    )
    key = "catalog/3/obverse/ddd_600.webp"
    media = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key}
    )
    storage = FakeStorage({key: _round_coin_jpeg()})

    candidates, _ = await rpb.find_candidates(db_session, only_ids=None)
    outcome = await rpb.process_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.cut == 1
    assert outcome.applied == 1
    assert not outcome.failed

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key is not None
    assert rpb.is_already_processed(refreshed.storage_key)
    assert refreshed.storage_key in storage.objects
    assert key in storage.objects  # the original is never removed


async def test_a_rectangular_photo_is_skipped_and_left_alone(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Blister pack", year=2023
    )
    key = "catalog/4/obverse/eee_600.webp"
    media = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key}
    )
    storage = FakeStorage({key: _square_blister_jpeg()})

    candidates, _ = await rpb.find_candidates(db_session, only_ids=None)
    outcome = await rpb.process_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.cut == 0
    assert outcome.skipped_by_reason == {"skip:not_round": 1}

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == key


async def test_find_trim_candidates_only_already_cut_rows(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Already cut", year=2020
    )
    nobg_key = "catalog/5/obverse/fff-nobg_600.webp"
    nobg = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=nobg_key, variants={"600": nobg_key}
    )
    not_yet_key = "catalog/5/obverse/ggg_600.webp"
    await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=not_yet_key,
        variants={"600": not_yet_key},
    )
    await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=None,
        external_url="https://i.ucoin.net/x.jpg",
    )

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)

    assert [c.media_id for c in candidates] == [nobg.id]
    assert candidates[0].source_key == nobg_key


async def test_trim_dry_run_computes_smaller_size_without_writing(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Wide margin", year=2021
    )
    key = "catalog/6/obverse/hhh-nobg_600.webp"
    media = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key}
    )
    storage = FakeStorage({key: _nobg_round_coin_webp()})

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome = await rpb.process_trim_candidates(
        db_session, storage, candidates, apply=False, log=lambda _: None
    )

    assert outcome.trimmed == 1
    assert outcome.unchanged == 0
    assert outcome.applied == 0
    assert set(storage.objects) == {key}  # nothing new written

    row = outcome.rows[0]
    assert row.new_size is not None
    assert row.new_size[0] < row.old_size[0]
    assert row.new_size[1] < row.old_size[1]

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == key  # untouched


async def test_trim_apply_rewrites_same_key_and_second_pass_is_a_no_op(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Trim me", year=2022
    )
    key = "catalog/7/obverse/iii-nobg_600.webp"
    media = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key}
    )
    storage = FakeStorage({key: _nobg_round_coin_webp()})

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome = await rpb.process_trim_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.trimmed == 1
    assert outcome.applied == 1
    assert not outcome.failed

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert rpb.is_already_processed(refreshed.storage_key)  # still the same -nobg base
    assert refreshed.storage_key.startswith(rpb.base_of(key))

    candidates_2 = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome_2 = await rpb.process_trim_candidates(
        db_session, storage, candidates_2, apply=True, log=lambda _: None
    )

    assert outcome_2.trimmed == 0
    assert outcome_2.unchanged == 1
    assert outcome_2.applied == 0


async def test_trim_skips_rows_not_yet_cut(db_session: AsyncSession, rpb: ModuleType) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Not cut yet", year=2023
    )
    key = "catalog/8/obverse/jjj_600.webp"
    await _make_media(db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key})

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)

    assert candidates == []
