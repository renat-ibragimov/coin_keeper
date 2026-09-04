"""Storage keys for the three sizes of one image (docs/06-media-storage.md).

    catalog/{catalog_item_id}/{role}/{name}_300.webp
    catalog/{catalog_item_id}/{role}/{name}_600.webp
    catalog/{catalog_item_id}/{role}/{name}_1200.webp

The key carries the size so a bucket listing is readable and a stale variant
cannot hide behind a name that says nothing.
"""

from __future__ import annotations

from app.core.images import LARGE_SIDE, PREVIEW_SIDE, VARIANT_SIDES

EXTENSION = ".webp"


def variant_key(base: str, side: int) -> str:
    return f"{base}_{side}{EXTENSION}"


def variant_keys(base: str) -> dict[int, str]:
    return {side: variant_key(base, side) for side in VARIANT_SIDES}


def catalog_base(catalog_item_id: int, role: str, name: str) -> str:
    return f"catalog/{catalog_item_id}/{role}/{name}"


def collection_base(owner_id: int, collection_item_id: int, role: str, name: str) -> str:
    return f"users/{owner_id}/{collection_item_id}/{role}/{name}"


def stored_variants(keys: dict[int, str]) -> dict[str, str]:
    """The JSONB shape of media_files.variants: string keys, as JSON has."""
    return {str(side): key for side, key in sorted(keys.items())}


def primary_key_of(keys: dict[int, str]) -> str:
    """What storage_key points at: the largest size stored."""
    return keys[max(keys)] if keys else variant_key("", LARGE_SIDE)


def preview_key_of(keys: dict[int, str]) -> str | None:
    return keys.get(PREVIEW_SIDE)
