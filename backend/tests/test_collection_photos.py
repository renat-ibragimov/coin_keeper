"""User photos of a collection instance: upload, replace, remove — and the
one thing that must never happen, the catalog's own media staying untouched
(docs/media.md, "Provenance and rights").

Storage is an in-memory stand-in patched over both `_storage()` singletons
that ever hand out a bucket client: `collection_photos` (where the service
puts/deletes objects) and `media_urls` (where CollectionService signs the URLs
a GET/POST response carries) — the real deployment is one MinIO bucket behind
both, so the fake must be one dict behind both too.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Iterator
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.images import MAX_SOURCE_BYTES
from app.core.mail.base import EmailMessage
from app.models import MediaFile
from app.models.enums import MediaRole, MediaSource
from app.services import collection_photos, media_urls
from tests.helpers import register_and_verify
from tests.seed import make_catalog_item, seed_reference

COLLECTION_PATH = "/api/v1/collection"


class FakeStorage:
    """Stands in for MinIO: an in-memory dict, keyed like the real bucket."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self.objects[key] = payload

    def delete_many(self, keys: Iterable[str]) -> None:
        for key in keys:
            self.objects.pop(key, None)

    def presigned_get_url(self, key: str, expires_seconds: int = 3600) -> str:
        return f"https://storage.example/{key}?signature=test&expires={expires_seconds}"


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeStorage]:
    fake = FakeStorage()
    monkeypatch.setattr(collection_photos, "_storage", lambda: fake)
    monkeypatch.setattr(media_urls, "_storage", lambda: fake)
    yield fake


def coin_jpeg(*, size: int = 900, color: tuple[int, int, int] = (40, 90, 160)) -> bytes:
    """A colour that is neither the white nor the black classify() treats as a
    cuttable background, so the stored bytes are the source untouched."""
    image = Image.new("RGB", (size, size), color)
    ImageDraw.Draw(image).ellipse(
        (size // 4, size // 4, size * 3 // 4, size * 3 // 4), fill=(210, 180, 120)
    )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def ctx(
    client: AsyncClient, db_session: AsyncSession, mail_outbox: list[EmailMessage]
) -> SimpleNamespace:
    refs = await seed_reference(db_session)
    _email_a, token_a = await register_and_verify(client, mail_outbox)
    _email_b, token_b = await register_and_verify(client, mail_outbox)
    item = await make_catalog_item(
        db_session, country=refs.ukraine, title="Дельфін", year=2018, denomination=refs.uah_2
    )
    db_session.add(
        MediaFile(
            catalog_item_id=item.id,
            role=MediaRole.OBVERSE,
            source=MediaSource.NBU,
            storage_key="catalog/1/obverse/official_1200.webp",
            thumbnail_key="catalog/1/obverse/official_300.webp",
            variants={
                "300": "catalog/1/obverse/official_300.webp",
                "1200": "catalog/1/obverse/official_1200.webp",
            },
            attribution="Національний банк України",
        )
    )
    db_session.add(
        MediaFile(
            catalog_item_id=item.id,
            role=MediaRole.REVERSE,
            source=MediaSource.NBU,
            storage_key="catalog/1/reverse/official_1200.webp",
            thumbnail_key="catalog/1/reverse/official_300.webp",
            variants={
                "300": "catalog/1/reverse/official_300.webp",
                "1200": "catalog/1/reverse/official_1200.webp",
            },
            attribution="Національний банк України",
        )
    )
    await db_session.commit()

    purchase = await client.post(
        COLLECTION_PATH,
        json={
            "catalogItemId": item.id,
            "price": "0",
            "currency": "UAH",
            "purchaseDate": "2024-01-15",
        },
        headers=_auth(token_a),
    )
    assert purchase.status_code == 201, purchase.text
    return SimpleNamespace(
        item_id=item.id,
        instance_id=purchase.json()["id"],
        token_a=token_a,
        token_b=token_b,
    )


async def test_upload_replace_and_remove_an_instance_photo(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"

    uploaded = await client.put(
        photo_url, content=coin_jpeg(), headers={**_auth(ctx.token_a), "Content-Type": "image/jpeg"}
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["obverse"]["medium"]
    # The reverse side is untouched by an obverse upload: still the catalog photo.
    assert "catalog/1/reverse/official" in body["reverse"]["medium"]

    obverse_keys = [
        key for key in storage.objects if "/obverse/" in key and key.startswith("users/")
    ]
    assert obverse_keys

    instance = await client.get(f"{COLLECTION_PATH}/{ctx.instance_id}", headers=_auth(ctx.token_a))
    assert instance.status_code == 200
    coin = instance.json()
    assert "users/" in coin["obverseImage"]["medium"]
    assert "catalog/1/reverse/official" in coin["reverseImage"]["medium"]

    first_upload_keys = set(obverse_keys)

    # A different picture moves the key; the previous object and row are gone.
    replaced = await client.put(
        photo_url,
        content=coin_jpeg(color=(90, 40, 160)),
        headers={**_auth(ctx.token_a), "Content-Type": "image/jpeg"},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["obverse"]["medium"] != body["obverse"]["medium"]
    assert not first_upload_keys & set(storage.objects)

    removed = await client.delete(photo_url, headers=_auth(ctx.token_a))
    assert removed.status_code == 200
    assert "catalog/1/obverse/official" in removed.json()["obverse"]["medium"]
    assert not any(key.startswith("users/") for key in storage.objects)

    # Removing what is already gone is not an error.
    again = await client.delete(photo_url, headers=_auth(ctx.token_a))
    assert again.status_code == 200
    assert "catalog/1/obverse/official" in again.json()["obverse"]["medium"]


def transparent_circle_png(*, size: int = 900) -> bytes:
    """A round, browser-cropped coin photo: opaque circle, transparent corners
    (docs/media.md — the round crop's own alpha channel)."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((0, 0, size - 1, size - 1), fill=(40, 90, 160, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def test_a_transparent_upload_keeps_its_alpha_channel_through_every_variant(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    """The round coin-photo crop uploads RGBA — process_image must neither
    flatten it onto an opaque background nor run the white/black background
    cut meant for a plain rectangular source (app/core/images.py)."""
    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"

    uploaded = await client.put(
        photo_url,
        content=transparent_circle_png(),
        headers={**_auth(ctx.token_a), "Content-Type": "image/png"},
    )
    assert uploaded.status_code == 200, uploaded.text

    obverse_keys = [
        key for key in storage.objects if "/obverse/" in key and key.startswith("users/")
    ]
    assert obverse_keys
    for key in obverse_keys:
        variant = Image.open(io.BytesIO(storage.objects[key]))
        assert variant.mode == "RGBA"
        assert variant.getpixel((0, 0))[3] == 0
        assert variant.getpixel((variant.width // 2, variant.height // 2))[3] == 255


async def test_the_catalog_photo_is_never_touched(
    client: AsyncClient, db_session: AsyncSession, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    storage.objects["catalog/1/obverse/official_1200.webp"] = b"nbu original bytes"
    storage.objects["catalog/1/obverse/official_300.webp"] = b"nbu preview bytes"

    catalog_row_before = (
        await db_session.execute(
            select(MediaFile).where(
                MediaFile.catalog_item_id == ctx.item_id,
                MediaFile.role == MediaRole.OBVERSE,
                MediaFile.source == MediaSource.NBU,
            )
        )
    ).scalar_one()
    before_id, before_key = catalog_row_before.id, catalog_row_before.storage_key

    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"
    for content in (coin_jpeg(), coin_jpeg(color=(10, 200, 30))):
        response = await client.put(
            photo_url, content=content, headers={**_auth(ctx.token_a), "Content-Type": "image/jpeg"}
        )
        assert response.status_code == 200, response.text
    assert (await client.delete(photo_url, headers=_auth(ctx.token_a))).status_code == 200

    catalog_row_after = await db_session.get(MediaFile, before_id)
    assert catalog_row_after is not None
    assert catalog_row_after.storage_key == before_key
    assert catalog_row_after.source == MediaSource.NBU
    assert storage.objects["catalog/1/obverse/official_1200.webp"] == b"nbu original bytes"
    assert storage.objects["catalog/1/obverse/official_300.webp"] == b"nbu preview bytes"


async def test_a_users_photo_is_isolated_from_other_users_and_the_catalog(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"
    uploaded = await client.put(
        photo_url, content=coin_jpeg(), headers={**_auth(ctx.token_a), "Content-Type": "image/jpeg"}
    )
    assert uploaded.status_code == 200, uploaded.text

    # Another user's card for the same catalog item never sees it.
    card = await client.get(f"/api/v1/catalog/{ctx.item_id}", headers=_auth(ctx.token_b))
    assert card.status_code == 200
    assert "users/" not in (card.json()["obverseImage"] or {}).get("medium", "")

    # Nor can the second user reach the first user's instance at all.
    other_put = await client.put(
        photo_url, content=coin_jpeg(), headers={**_auth(ctx.token_b), "Content-Type": "image/jpeg"}
    )
    assert other_put.status_code == 404

    other_delete = await client.delete(photo_url, headers=_auth(ctx.token_b))
    assert other_delete.status_code == 404


async def test_a_non_image_payload_is_rejected(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"
    response = await client.put(
        photo_url,
        content=b"this is not a picture, it is a sentence",
        headers={**_auth(ctx.token_a), "Content-Type": "image/jpeg"},
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-image")
    assert not any(key.startswith("users/") for key in storage.objects)


async def test_an_oversized_upload_is_refused_from_the_header(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"
    response = await client.put(
        photo_url,
        content=coin_jpeg(),
        headers={
            **_auth(ctx.token_a),
            "Content-Type": "image/jpeg",
            "Content-Length": str(MAX_SOURCE_BYTES + 1),
        },
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-image")


async def test_an_invalid_role_is_rejected(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    response = await client.put(
        f"{COLLECTION_PATH}/{ctx.instance_id}/photos/edge",
        content=coin_jpeg(),
        headers={**_auth(ctx.token_a), "Content-Type": "image/jpeg"},
    )
    assert response.status_code == 422


async def test_photo_endpoints_require_a_token(
    client: AsyncClient, storage: FakeStorage, ctx: SimpleNamespace
) -> None:
    photo_url = f"{COLLECTION_PATH}/{ctx.instance_id}/photos/obverse"
    assert (await client.put(photo_url, content=coin_jpeg())).status_code == 401
    assert (await client.delete(photo_url)).status_code == 401
