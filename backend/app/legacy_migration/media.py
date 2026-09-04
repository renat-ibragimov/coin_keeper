"""Migration of media_files: path split, provenance and image processing.

Rules: docs/09-data-migration.md, the section on splitting image paths, and
docs/06-media-storage.md.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.images import ImageRejectedError, ProcessedImage, process_image
from app.core.media_keys import (
    catalog_base,
    collection_base,
    preview_key_of,
    primary_key_of,
    variant_key,
    variant_keys,
)
from app.models.enums import MediaSource

UCOIN_MARKERS = ("ucoin.net", "ucoin.")
EXTERNAL_PREFIXES = ("http://", "https://")

_SEPARATORS = re.compile(r"[\\/]")
# "C:name.jpg" is drive-relative on Windows; the drive letter is not part of
# the file name.
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


@dataclass(slots=True)
class PreparedMedia:
    legacy_id: int
    catalog_item_id: int | None
    collection_item_id: int | None
    role: str
    source: MediaSource
    external_url: str | None = None
    storage_key: str | None = None
    thumbnail_key: str | None = None
    variants: dict[int, str] = field(default_factory=dict)
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    processed: ProcessedImage | None = None


@dataclass(slots=True)
class MediaOutcome:
    """One of: prepared row, missing file, or rejected payload."""

    prepared: PreparedMedia | None = None
    missing_path: str | None = None
    rejected: tuple[str, str] | None = None


def is_external(original_path: str) -> bool:
    return original_path.strip().lower().startswith(EXTERNAL_PREFIXES)


def file_name_from(original_path: str) -> str:
    r"""Last component of a path written by either platform.

    The desktop application ran on Windows and stored absolute paths: a drive
    letter, backslashes and spaces in the directory names, for example

        C:\Users\<user>\AppData\Roaming\CoinKeeper Data\media\5_obverse_<uuid>.jpg

    pathlib.Path on POSIX does not treat a backslash as a separator, so .name
    on such a value returns the whole string and every file lookup misses --
    which is what the first real dry run showed: 2270 local rows, zero found.

    Splitting on both separators works wherever the path was written and
    leaves a bare file name untouched. The name is returned as stored,
    including the case of its extension.
    """
    tail = _SEPARATORS.split(original_path.strip())[-1]
    return _DRIVE_PREFIX.sub("", tail)


def looks_like_ucoin(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in UCOIN_MARKERS)


def resolve_local_source(
    catalog_item_id: int | None,
    ucoin_catalog_items: frozenset[int],
) -> MediaSource:
    """Provenance of a local file.

    There is no field in the legacy schema saying where a local file came from.
    The signal available is whether the coin itself is known to come from
    uCoin — via source_key or a price_source_links row. When it does, its
    catalog images almost certainly came from there too.

    Ambiguity resolves to `ucoin`, the stricter option: getting it wrong that
    way hides a photo from strangers, getting it wrong the other way publishes
    someone else's (docs/09-data-migration.md).
    """
    if catalog_item_id is not None and catalog_item_id in ucoin_catalog_items:
        return MediaSource.UCOIN
    return MediaSource.USER_UPLOAD


def storage_base_for(row: Mapping[str, Any], *, owner_id: int) -> str:
    """Layout from docs/06-media-storage.md, without the size and extension."""
    role = str(row["role"])
    name = f"legacy-{row['id']}"
    if row.get("collection_item_id"):
        return collection_base(owner_id, int(row["collection_item_id"]), role, name)
    return catalog_base(int(row["catalog_item_id"]), role, name)


def prepare(
    row: Mapping[str, Any],
    *,
    owner_id: int,
    media_root: Path | None,
    ucoin_catalog_items: frozenset[int],
    process: bool,
) -> MediaOutcome:
    """Turn one legacy media row into something insertable.

    `process` is False for --skip-media: the row is still classified and the
    keys are still assigned, the bytes are simply not read or uploaded.
    """
    original_path = str(row.get("original_path") or "").strip()
    legacy_id = int(row["id"])
    role = str(row["role"]).strip().lower()

    if is_external(original_path):
        return MediaOutcome(
            prepared=PreparedMedia(
                legacy_id=legacy_id,
                catalog_item_id=row.get("catalog_item_id"),
                collection_item_id=row.get("collection_item_id"),
                role=role,
                # External links are uCoin hotlinks; anything ambiguous is
                # treated the same, stricter way.
                source=MediaSource.UCOIN,
                external_url=original_path,
                mime_type=row.get("mime_type"),
                width=row.get("width"),
                height=row.get("height"),
                sha256=row.get("sha256"),
            )
        )

    if not original_path:
        # Neither a file nor a link: nothing to migrate.
        return MediaOutcome(missing_path="")

    source = resolve_local_source(row.get("catalog_item_id"), ucoin_catalog_items)
    keys = variant_keys(storage_base_for(row, owner_id=owner_id))
    prepared = PreparedMedia(
        legacy_id=legacy_id,
        catalog_item_id=row.get("catalog_item_id"),
        collection_item_id=row.get("collection_item_id"),
        role=role,
        source=source,
        storage_key=primary_key_of(keys),
        thumbnail_key=preview_key_of(keys),
        variants=keys,
        mime_type="image/webp",
    )

    if not process or media_root is None:
        return MediaOutcome(prepared=prepared)

    file_path = media_root / file_name_from(original_path)
    if not file_path.is_file():
        # The row is dropped only when it has neither a file nor a link.
        return MediaOutcome(missing_path=original_path)

    try:
        processed = process_image(file_path.read_bytes())
    except ImageRejectedError as exc:
        return MediaOutcome(rejected=(original_path, str(exc)))

    # A legacy original is often smaller than 1200 px, so fewer sizes come
    # out than were reserved; the row must name what was really stored.
    prepared.variants = {
        side: variant_key(storage_base_for(row, owner_id=owner_id), side)
        for side in processed.processed_sides()
    }
    prepared.storage_key = primary_key_of(prepared.variants)
    prepared.thumbnail_key = preview_key_of(prepared.variants)
    prepared.processed = processed
    prepared.width = processed.width
    prepared.height = processed.height
    prepared.size_bytes = processed.size_bytes
    prepared.sha256 = processed.sha256
    return MediaOutcome(prepared=prepared)
