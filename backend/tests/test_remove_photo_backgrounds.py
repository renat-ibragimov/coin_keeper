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

    def head(self, key: str) -> int | None:
        payload = self.objects.get(key)
        return None if payload is None else len(payload)

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


def _transparent_original_webp(side: int = 600) -> bytes:
    """An NBU original already cut upstream: transparent corners over a black matte.

    Stands in for the corrupted-run incident's real source shape -- alpha=0
    everywhere except an opaque disc in the middle, with whatever RGB the
    matte happens to carry (here, an arbitrary dark color) sitting underneath
    the transparency.
    """
    img = Image.new("RGBA", (side, side), (20, 20, 20, 0))
    margin = side // 4
    ImageDraw.Draw(img).ellipse(
        (margin, margin, side - margin, side - margin), fill=(150, 120, 40, 255)
    )
    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", lossless=True)
    return buffer.getvalue()


def _opaque_dark_original_jpeg(side: int = 600) -> bytes:
    """A legitimate dark-background original: no alpha channel at all."""
    img = Image.new("RGB", (side, side), (20, 20, 20))
    margin = side // 4
    ImageDraw.Draw(img).ellipse((margin, margin, side - margin, side - margin), fill=(150, 120, 40))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=95)
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


async def test_an_already_transparent_original_is_skipped_not_recut(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    """Regression guard for the 2026-09 incident: see docs/06-media-storage.md.

    Feeding the main --apply pass a source that already carries meaningful
    transparency must not flatten it to RGB and read its matte as a dark
    background -- it must come back as skip:already_transparent, untouched.
    """
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Already transparent", year=2020
    )
    key = "catalog/9/obverse/kkk_600.webp"
    media = await _make_media(
        db_session, catalog_item_id=item.id, storage_key=key, variants={"600": key}
    )
    storage = FakeStorage({key: _transparent_original_webp()})

    candidates, _ = await rpb.find_candidates(db_session, only_ids=None)
    outcome = await rpb.process_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.cut == 0
    assert outcome.skipped_by_reason == {"skip:already_transparent": 1}

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == key  # untouched


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


async def test_revert_dry_run_finds_a_corrupted_row_without_writing(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    """The original was already transparent -- this row is the incident's damage."""
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Corrupted by the dark run", year=2020
    )
    nobg_key = "catalog/10/obverse/lll-nobg_1200.webp"
    media = await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=nobg_key,
        variants={"1200": nobg_key},
    )
    original_600 = "catalog/10/obverse/lll_600.webp"
    storage = FakeStorage(
        {nobg_key: b"whatever the wrong cut wrote", original_600: _transparent_original_webp(600)}
    )

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome = await rpb.process_revert_candidates(
        db_session, storage, candidates, apply=False, log=lambda _: None
    )

    assert outcome.candidates == 1
    assert outcome.needs_revert == 1
    assert outcome.reverted == 0
    assert not outcome.failed
    row = outcome.rows[0]
    assert row.status == rpb.REVERT_STATUS_NEEDS_REVERT
    assert row.transparent_fraction is not None and row.transparent_fraction > 0.3

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == nobg_key  # untouched
    assert original_600 in storage.objects  # original never touched either
    assert set(storage.objects) == {nobg_key, original_600}  # nothing new written


async def test_revert_apply_points_the_row_back_at_the_original(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Revert me", year=2020
    )
    nobg_key = "catalog/11/obverse/mmm-nobg_1200.webp"
    media = await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=nobg_key,
        variants={"1200": nobg_key},
    )
    original_600 = "catalog/11/obverse/mmm_600.webp"
    original_bytes = _transparent_original_webp(600)
    storage = FakeStorage({nobg_key: b"whatever the wrong cut wrote", original_600: original_bytes})

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome = await rpb.process_revert_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.needs_revert == 1
    assert outcome.reverted == 1
    assert not outcome.failed

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key is not None
    assert not rpb.is_already_processed(refreshed.storage_key)
    assert refreshed.storage_key.startswith("catalog/11/obverse/mmm_")
    # The untouched surviving variant is kept as-is, not re-encoded.
    assert original_600 in refreshed.variants.values()
    assert storage.objects[original_600] == original_bytes
    # A side missing in storage (300, 1200) is regenerated from the original.
    assert "catalog/11/obverse/mmm_300.webp" in storage.objects
    assert nobg_key in storage.objects  # the -nobg object is never deleted

    # Idempotent: a second pass no longer sees this row at all.
    candidates_2 = await rpb.find_trim_candidates(db_session, only_ids=None)
    assert candidates_2 == []


async def test_revert_leaves_a_legitimate_dark_cut_alone(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Legitimate dark cut", year=2020
    )
    nobg_key = "catalog/12/obverse/nnn-nobg_1200.webp"
    media = await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=nobg_key,
        variants={"1200": nobg_key},
    )
    original_600 = "catalog/12/obverse/nnn_600.webp"
    storage = FakeStorage(
        {nobg_key: b"a correctly cut dark coin", original_600: _opaque_dark_original_jpeg(600)}
    )

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome = await rpb.process_revert_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.needs_revert == 0
    assert outcome.not_needed == 1
    assert outcome.reverted == 0

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == nobg_key  # untouched
    assert set(storage.objects) == {nobg_key, original_600}  # nothing new written


async def test_revert_reports_a_missing_original_without_crashing(
    db_session: AsyncSession, rpb: ModuleType
) -> None:
    reference = await seed_reference(db_session)
    item = await make_catalog_item(
        db_session, country=reference.ukraine, title="Original is gone", year=2020
    )
    nobg_key = "catalog/13/obverse/ooo-nobg_1200.webp"
    media = await _make_media(
        db_session,
        catalog_item_id=item.id,
        storage_key=nobg_key,
        variants={"1200": nobg_key},
    )
    storage = FakeStorage({nobg_key: b"the only surviving object"})

    candidates = await rpb.find_trim_candidates(db_session, only_ids=None)
    outcome = await rpb.process_revert_candidates(
        db_session, storage, candidates, apply=True, log=lambda _: None
    )

    assert outcome.missing_original == 1
    assert outcome.needs_revert == 0
    assert not outcome.failed  # missing_original is its own status, not a crash
    assert outcome.rows[0].status == rpb.REVERT_STATUS_MISSING_ORIGINAL

    refreshed = (
        await db_session.execute(select(MediaFile).where(MediaFile.id == media.id))
    ).scalar_one()
    assert refreshed.storage_key == nobg_key  # untouched
