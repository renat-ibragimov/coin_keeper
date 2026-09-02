"""Full migration run against the synthetic legacy fixture.

The owner's real database is not in the repository, so everything here runs on
tests/fixtures/build_legacy_db.py. Its counts are small but its shapes are the
real ones — same DDL, same edge cases.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.legacy_migration import prices
from app.legacy_migration.report import MigrationReport
from app.legacy_migration.runner import MigrationError, MigrationOptions, MigrationRunner
from app.models import (
    CatalogItem,
    CollectionItem,
    Expense,
    MarketPriceSnapshot,
    MediaFile,
    User,
    UserSettings,
)
from app.models.enums import MediaSource, UserRole
from tests.fixtures.build_legacy_db import (
    COLLECTION_MEDIA_FILENAME,
    EXPECTED_COUNTS,
    EXPECTED_EXPENSE_SUM,
    EXPECTED_MIGRATED,
    EXPECTED_MIGRATED_SKIP_MEDIA,
    PRESENT_MEDIA_FILENAME,
    build,
)

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "migration-password"


class RecordingStorage:
    """Stands in for MinIO: records keys instead of talking to S3."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self.objects[key] = payload

    def ensure_bucket(self) -> None:
        return None


def _write_jpeg(path: Path, size: tuple[int, int] = (400, 400)) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", size, (180, 140, 60)).save(buffer, format="JPEG")
    path.write_bytes(buffer.getvalue())


@pytest.fixture
def legacy_db(tmp_path: Path) -> Iterator[Path]:
    yield build(tmp_path / "legacy.db")


@pytest.fixture
def media_root(tmp_path: Path) -> Path:
    root = tmp_path / "media"
    root.mkdir()
    _write_jpeg(root / PRESENT_MEDIA_FILENAME)
    _write_jpeg(root / COLLECTION_MEDIA_FILENAME)
    # The file for MISSING_MEDIA_FILENAME is deliberately absent.
    return root


def _options(legacy_db: Path, **overrides: object) -> MigrationOptions:
    base = {
        "sqlite_path": legacy_db,
        "media_path": None,
        "owner_email": OWNER_EMAIL,
        "owner_password": OWNER_PASSWORD,
    }
    base.update(overrides)
    return MigrationOptions(**base)  # type: ignore[arg-type]


async def _run(
    session: AsyncSession, options: MigrationOptions, storage: object = None
) -> MigrationReport:
    report = MigrationReport()
    runner = MigrationRunner(session, options, report, storage=storage)
    return await runner.run()


# --------------------------------------------------------------- full run


async def test_full_run_migrates_every_table(db_session: AsyncSession, legacy_db: Path) -> None:
    report = await _run(db_session, _options(legacy_db, skip_media=True))

    assert report.checks_passed, [c for c in report.checks if not c["passed"]]
    for table, expected in EXPECTED_MIGRATED_SKIP_MEDIA.items():
        if table in report.migrated:
            assert report.migrated[table] == expected, table

    counts = {
        CatalogItem: EXPECTED_MIGRATED["catalog_items"],
        CollectionItem: EXPECTED_MIGRATED["collection_items"],
        MarketPriceSnapshot: EXPECTED_MIGRATED["market_price_snapshots"],
        Expense: EXPECTED_MIGRATED["expenses"],
    }
    for model, expected in counts.items():
        actual = await db_session.scalar(select(func.count()).select_from(model))
        assert actual == expected, model.__name__


async def test_row_with_a_dangling_reference_is_dropped_and_reported(
    db_session: AsyncSession, legacy_db: Path
) -> None:
    """SQLite does not enforce foreign keys; PostgreSQL does.

    Without this guard the whole run would die on an opaque asyncpg error
    partway through, after several tables had already been committed.
    """
    report = await _run(db_session, _options(legacy_db, skip_media=True))

    assert report.skipped.get("market_price_snapshots_dangling_reference") == 1
    assert any("currency_code" in w for w in report.conversion_warnings)

    # The row is absent, and the reconcile check still adds up.
    orphan = await db_session.get(MarketPriceSnapshot, 8)
    assert orphan is None
    reconcile = next(c for c in report.checks if c["name"] == "reconcile:market_price_snapshots")
    assert reconcile["passed"], reconcile


async def test_owner_is_created_ready_to_use(db_session: AsyncSession, legacy_db: Path) -> None:
    """No registration: verified, active and admin from the start."""
    await _run(db_session, _options(legacy_db, skip_media=True))

    owner = await db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    assert owner.role is UserRole.ADMIN
    assert owner.email_verified is True
    assert owner.is_active is True
    # The password is hashed with the application's own hasher, not stored raw.
    assert owner.password_hash != OWNER_PASSWORD
    assert owner.password_hash.startswith("$argon2")

    settings = await db_session.scalar(select(UserSettings).where(UserSettings.user_id == owner.id))
    assert settings is not None
    # Carried over from the legacy key/value settings table.
    assert settings.default_grade_circulation == "XF"


async def test_catalog_becomes_the_shared_one(db_session: AsyncSession, legacy_db: Path) -> None:
    await _run(db_session, _options(legacy_db, skip_media=True))

    personal = await db_session.scalar(
        select(func.count()).select_from(CatalogItem).where(CatalogItem.created_by.is_not(None))
    )
    assert personal == 0

    archived = await db_session.scalar(
        select(func.count()).select_from(CatalogItem).where(CatalogItem.is_archived)
    )
    assert archived == 0


async def test_personal_rows_belong_to_the_owner(db_session: AsyncSession, legacy_db: Path) -> None:
    await _run(db_session, _options(legacy_db, skip_media=True))
    owner_id = await db_session.scalar(select(User.id).where(User.email == OWNER_EMAIL))

    for model in (CollectionItem, Expense):
        orphans = await db_session.scalar(
            select(func.count()).select_from(model).where(model.owner_id != owner_id)
        )
        assert orphans == 0, model.__name__


async def test_expense_sum_matches_the_source_to_the_kopeck(
    db_session: AsyncSession, legacy_db: Path
) -> None:
    report = await _run(db_session, _options(legacy_db, skip_media=True))

    total = await db_session.scalar(select(func.sum(Expense.amount)))
    assert total == Decimal(EXPECTED_EXPENSE_SUM)

    check = next(c for c in report.checks if c["name"] == "sum:expenses.amount")
    assert check["passed"], check


async def test_null_metal_kind_becomes_unknown(db_session: AsyncSession, legacy_db: Path) -> None:
    """Nullable in the legacy schema, NOT NULL in the new one."""
    await _run(db_session, _options(legacy_db, skip_media=True))
    item = await db_session.get(CatalogItem, 5)
    assert item is not None
    assert item.metal_kind.value == "unknown"


async def test_naive_timestamps_are_stored_as_utc(
    db_session: AsyncSession, legacy_db: Path
) -> None:
    await _run(db_session, _options(legacy_db, skip_media=True))
    snapshot = await db_session.get(MarketPriceSnapshot, 5)
    assert snapshot is not None
    assert snapshot.observed_at.tzinfo is not None
    assert snapshot.observed_at.utcoffset() is not None
    assert snapshot.observed_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


# ------------------------------------------------------------ price flags


async def test_suspect_flags_are_set_per_rule(db_session: AsyncSession, legacy_db: Path) -> None:
    report = await _run(db_session, _options(legacy_db, skip_media=True))

    # Glued number, price equal to the issue year, zero.
    # Snapshot 8 also fails, but on a dangling currency reference, so it never
    # reaches the database at all.
    for snapshot_id in (4, 5, 6):
        snapshot = await db_session.get(MarketPriceSnapshot, snapshot_id)
        assert snapshot is not None
        assert snapshot.is_suspect is True, snapshot_id

    # The three sane prices on item 1 stay clean.
    for snapshot_id in (1, 2, 3):
        snapshot = await db_session.get(MarketPriceSnapshot, snapshot_id)
        assert snapshot is not None
        assert snapshot.is_suspect is False, snapshot_id

    assert report.suspect_total == 4
    for rule in (
        prices.RULE_RANGE,
        prices.RULE_LOOKS_LIKE_YEAR,
        prices.RULE_DIGIT_RUN,
        prices.RULE_CURRENCY,
        prices.RULE_DEVIATION,
    ):
        assert report.suspect_by_rule.get(rule, 0) > 0, rule
        assert report.suspect_examples[rule], rule


async def test_invalid_json_payload_becomes_null_and_is_reported(
    db_session: AsyncSession, legacy_db: Path
) -> None:
    report = await _run(db_session, _options(legacy_db, skip_media=True))

    snapshot = await db_session.get(MarketPriceSnapshot, 7)
    assert snapshot is not None
    assert snapshot.raw_payload is None
    assert 7 in report.invalid_json_payloads


async def test_snapshots_are_migrated_as_shared(db_session: AsyncSession, legacy_db: Path) -> None:
    await _run(db_session, _options(legacy_db, skip_media=True))
    personal = await db_session.scalar(
        select(func.count())
        .select_from(MarketPriceSnapshot)
        .where(MarketPriceSnapshot.created_by.is_not(None))
    )
    assert personal == 0


# ----------------------------------------------------------------- media


async def test_media_split_and_provenance(
    db_session: AsyncSession, legacy_db: Path, media_root: Path
) -> None:
    storage = RecordingStorage()
    report = await _run(db_session, _options(legacy_db, media_path=media_root), storage=storage)

    external = await db_session.scalars(
        select(MediaFile).where(MediaFile.external_url.is_not(None))
    )
    external_rows = list(external)
    assert len(external_rows) == 2
    # External links are uCoin hotlinks; anything ambiguous is treated the same.
    assert all(row.source is MediaSource.UCOIN for row in external_rows)
    assert all(row.storage_key is None for row in external_rows)

    stored = list(
        await db_session.scalars(select(MediaFile).where(MediaFile.storage_key.is_not(None)))
    )
    assert len(stored) == 2
    assert all(row.external_url is None for row in stored)
    assert all(row.mime_type == "image/webp" for row in stored)
    assert all(row.sha256 and row.width and row.size_bytes for row in stored)

    # Photo on a coin traced to uCoin is uCoin's; the untraced one is the owner's.
    by_item = {row.catalog_item_id: row for row in stored}
    assert by_item[1].source is MediaSource.UCOIN
    assert by_item[3].source is MediaSource.USER_UPLOAD

    # The lost file is reported and its row dropped: no file, no link.
    assert len(report.media_missing_file) == 1
    assert report.skipped.get("media_files_without_file_or_url") == 1

    # Both the original and the thumbnail reached storage.
    assert len(storage.objects) == 4
    assert any(key.endswith("_thumb.webp") for key in storage.objects)


async def test_stored_images_are_webp_within_the_size_limit(
    db_session: AsyncSession, legacy_db: Path, media_root: Path
) -> None:
    storage = RecordingStorage()
    await _run(db_session, _options(legacy_db, media_path=media_root), storage=storage)

    for key, payload in storage.objects.items():
        with Image.open(io.BytesIO(payload)) as image:
            assert image.format == "WEBP"
            limit = 300 if key.endswith("_thumb.webp") else 1600
            assert max(image.size) <= limit


async def test_every_media_row_has_a_source(
    db_session: AsyncSession, legacy_db: Path, media_root: Path
) -> None:
    await _run(db_session, _options(legacy_db, media_path=media_root), storage=RecordingStorage())
    without_source = await db_session.scalar(
        select(func.count()).select_from(MediaFile).where(MediaFile.source.is_(None))
    )
    assert without_source == 0


async def test_skip_media_defers_the_whole_step(
    db_session: AsyncSession, legacy_db: Path, media_root: Path
) -> None:
    """--skip-media writes no media rows at all, rather than half of one.

    Writing them without processing would leave a storage_key pointing at an
    object that was never uploaded, and would keep rows whose file is missing,
    because the file system is never consulted.
    """
    storage = RecordingStorage()
    report = await _run(
        db_session,
        _options(legacy_db, media_path=media_root, skip_media=True),
        storage=storage,
    )
    assert storage.objects == {}
    total = await db_session.scalar(select(func.count()).select_from(MediaFile))
    assert total == 0
    assert report.skipped["media_files_deferred"] == EXPECTED_COUNTS["media_files"]
    # Deferred still reconciles: nothing went missing silently.
    reconcile = next(c for c in report.checks if c["name"] == "reconcile:media_files")
    assert reconcile["passed"], reconcile


async def test_media_can_be_filled_in_by_a_later_run(
    db_session: AsyncSession, legacy_db: Path, media_root: Path
) -> None:
    """The fast pass first, the images afterwards."""
    await _run(db_session, _options(legacy_db, skip_media=True))
    assert await db_session.scalar(select(func.count()).select_from(MediaFile)) == 0

    await _run(
        db_session,
        _options(legacy_db, media_path=media_root, resume=True),
        storage=RecordingStorage(),
    )
    total = await db_session.scalar(select(func.count()).select_from(MediaFile))
    assert total == EXPECTED_MIGRATED["media_files"]


# ------------------------------------------------------- idempotency, dry run


async def test_dry_run_writes_nothing(
    db_session: AsyncSession, legacy_db: Path, tmp_path: Path
) -> None:
    report = await _run(db_session, _options(legacy_db, dry_run=True, skip_media=True))

    for model in (User, CatalogItem, CollectionItem, Expense, MarketPriceSnapshot):
        count = await db_session.scalar(select(func.count()).select_from(model))
        assert count == 0, model.__name__

    # The report is still complete enough to judge the run by.
    assert report.migrated["catalog_items"] == EXPECTED_MIGRATED["catalog_items"]
    assert report.suspect_total == 4
    assert report.checks_passed

    path = tmp_path / "report.json"
    report.write(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dryRun"] is True
    assert payload["prices"]["suspectTotal"] == 4


async def test_second_run_needs_resume_and_changes_nothing(
    db_session: AsyncSession, legacy_db: Path
) -> None:
    await _run(db_session, _options(legacy_db, skip_media=True))

    before = {
        model.__name__: await db_session.scalar(select(func.count()).select_from(model))
        for model in (User, CatalogItem, CollectionItem, Expense, MarketPriceSnapshot, MediaFile)
    }

    # Without --resume a non-empty target is refused rather than half-merged.
    with pytest.raises(MigrationError, match="resume"):
        await _run(db_session, _options(legacy_db, skip_media=True))

    await _run(db_session, _options(legacy_db, skip_media=True, resume=True))

    after = {
        model.__name__: await db_session.scalar(select(func.count()).select_from(model))
        for model in (User, CatalogItem, CollectionItem, Expense, MarketPriceSnapshot, MediaFile)
    }
    assert after == before


async def test_expectations_profile_is_enforced(db_session: AsyncSession, legacy_db: Path) -> None:
    """A wrong profile must fail the run, not be quietly ignored."""
    report = await _run(
        db_session,
        _options(
            legacy_db,
            skip_media=True,
            expectations={"counts": {"catalog_items": 9999}, "expenseSum": "1.00"},
        ),
    )
    assert report.checks_passed is False
    failed = [c["name"] for c in report.checks if not c["passed"]]
    assert "expected:catalog_items" in failed
    assert "expected:sum:expenses.amount" in failed


async def test_report_never_contains_the_owner_address(
    db_session: AsyncSession, legacy_db: Path
) -> None:
    """Only the user id goes into the report (docs/09-data-migration.md)."""
    report = await _run(db_session, _options(legacy_db, skip_media=True))
    serialised = json.dumps(report.to_dict(), ensure_ascii=False)
    assert OWNER_EMAIL not in serialised
    assert OWNER_PASSWORD not in serialised
    assert report.owner_user_id is not None
