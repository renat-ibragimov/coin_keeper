"""The profile picture: upload, replace, remove, and what gets rejected.

Storage is an in-memory stand-in patched over `avatars._storage`, which is
where both the service and `user_out` reach for the bucket — so one fixture
covers the writes and the signed URL that comes back on /auth/me.
"""

from __future__ import annotations

import io
from collections.abc import Iterable, Iterator

import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw

from app.core.images import MAX_SOURCE_BYTES
from app.core.mail.base import EmailMessage
from app.services import avatars
from tests.helpers import register_and_verify

AVATAR_PATH = "/api/v1/auth/me/avatar"


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
    monkeypatch.setattr(avatars, "_storage", lambda: fake)
    yield fake


def portrait_jpeg(*, width: int = 800, height: int = 500) -> bytes:
    """A wide photo, so a square result proves the crop actually ran."""
    image = Image.new("RGB", (width, height), (40, 90, 160))
    ImageDraw.Draw(image).ellipse(
        (width // 2 - 120, height // 2 - 120, width // 2 + 120, height // 2 + 120),
        fill=(240, 210, 170),
    )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_upload_replace_and_remove_an_avatar(
    client: AsyncClient, mail_outbox: list[EmailMessage], storage: FakeStorage
) -> None:
    _, token = await register_and_verify(client, mail_outbox)
    headers = _auth(token)

    fresh = await client.get("/api/v1/auth/me", headers=headers)
    assert fresh.status_code == 200
    assert fresh.json()["avatarUrl"] is None

    uploaded = await client.put(
        AVATAR_PATH, content=portrait_jpeg(), headers={**headers, "Content-Type": "image/jpeg"}
    )
    assert uploaded.status_code == 200, uploaded.text
    url = uploaded.json()["avatarUrl"]
    assert url

    # One object, one size, and square whatever shape went in.
    assert len(storage.objects) == 1
    key, stored = next(iter(storage.objects.items()))
    assert key.startswith("users/") and key.endswith("_256.webp")
    with Image.open(io.BytesIO(stored)) as image:
        assert image.format == "WEBP"
        assert image.size == (256, 256)

    # The profile endpoint signs the same key, not some other one.
    again = await client.get("/api/v1/auth/me", headers=headers)
    assert again.json()["avatarUrl"] == url

    # A different picture moves the key, so no cached URL keeps serving the
    # old face — and the previous object does not linger behind it.
    replaced = await client.put(
        AVATAR_PATH,
        content=portrait_jpeg(width=600, height=900),
        headers={**headers, "Content-Type": "image/jpeg"},
    )
    assert replaced.status_code == 200
    assert replaced.json()["avatarUrl"] != url
    assert len(storage.objects) == 1
    assert key not in storage.objects

    removed = await client.delete(AVATAR_PATH, headers=headers)
    assert removed.status_code == 200
    assert removed.json()["avatarUrl"] is None
    assert storage.objects == {}

    # Removing what is already gone is not an error.
    assert (await client.delete(AVATAR_PATH, headers=headers)).status_code == 200


async def test_a_non_image_payload_is_rejected(
    client: AsyncClient, mail_outbox: list[EmailMessage], storage: FakeStorage
) -> None:
    _, token = await register_and_verify(client, mail_outbox)

    response = await client.put(
        AVATAR_PATH,
        content=b"this is not a picture, it is a sentence",
        headers={**_auth(token), "Content-Type": "image/jpeg"},
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-image")
    assert storage.objects == {}


async def test_an_oversized_upload_is_refused_from_the_header(
    client: AsyncClient, mail_outbox: list[EmailMessage], storage: FakeStorage
) -> None:
    """A declared length over the limit is answered without reading the body."""
    _, token = await register_and_verify(client, mail_outbox)

    response = await client.put(
        AVATAR_PATH,
        content=portrait_jpeg(),
        headers={
            **_auth(token),
            "Content-Type": "image/jpeg",
            "Content-Length": str(MAX_SOURCE_BYTES + 1),
        },
    )
    assert response.status_code == 422
    assert response.json()["type"].endswith("invalid-image")
    assert storage.objects == {}


async def test_avatar_endpoints_require_a_token(client: AsyncClient, storage: FakeStorage) -> None:
    assert (await client.put(AVATAR_PATH, content=portrait_jpeg())).status_code == 401
    assert (await client.delete(AVATAR_PATH)).status_code == 401
