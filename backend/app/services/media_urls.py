"""Choosing and signing catalog images for API payloads.

Selection order per role comes from docs/06-media-storage.md: the viewer's own
photo, then an official catalog one (nbu/manual), then a uCoin image — which is
only ever fetched for its importer, the repository already filters it out for
everyone else. Stored files are served through presigned URLs; hotlinks are
returned as they are.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.core.images import LARGE_SIDE, MEDIUM_SIDE, PREVIEW_SIDE
from app.core.storage import ObjectStorage, build_s3_client
from app.models import MediaFile
from app.models.enums import MediaRole, MediaSource

PRESIGN_TTL_SECONDS = 3600

_SOURCE_PRIORITY = {
    MediaSource.USER_UPLOAD: 0,
    MediaSource.NBU: 1,
    MediaSource.MANUAL: 1,
    MediaSource.UA_COINS: 2,
    MediaSource.UCOIN: 3,
}


@dataclass
class CoinImage:
    """One side of a coin at the sizes that are stored for it.

    A page picks by where it shows the coin — a listing takes the preview, a
    card the medium, the lightbox the large — and uses the next size up for a
    dense screen (docs/06-media-storage.md).
    """

    preview: str | None = None
    medium: str | None = None
    large: str | None = None
    attribution: str | None = None


@dataclass
class CatalogImages:
    obverse: CoinImage | None = None
    reverse: CoinImage | None = None
    thumbnail_url: str | None = None


@lru_cache
def _storage() -> ObjectStorage:
    settings = get_settings()
    presign_client = (
        build_s3_client(settings, endpoint_url=settings.s3_public_endpoint)
        if settings.s3_public_endpoint
        else None
    )
    return ObjectStorage(
        build_s3_client(settings), settings.s3_bucket, presign_client=presign_client
    )


class MediaUrlBuilder:
    def __init__(self, storage: ObjectStorage | None = None) -> None:
        self._storage = storage or _storage()

    def file_url(self, media: MediaFile) -> str | None:
        if media.storage_key:
            return self._storage.presigned_get_url(media.storage_key, PRESIGN_TTL_SECONDS)
        return media.external_url

    def thumbnail_url(self, media: MediaFile) -> str | None:
        if media.thumbnail_key:
            return self._storage.presigned_get_url(media.thumbnail_key, PRESIGN_TTL_SECONDS)
        return self.file_url(media)

    def image_of(self, media: MediaFile) -> CoinImage:
        """The stored sizes of one image.

        Rows written before the three-size layout have two keys and no
        variants; they answer with what they have rather than with nothing.
        """
        variants = media.variants or {}
        if not variants:
            whole = self.file_url(media)
            return CoinImage(
                preview=self.thumbnail_url(media),
                medium=whole,
                large=whole,
                attribution=media.attribution,
            )

        def at(side: int) -> str | None:
            key = variants.get(str(side))
            return self._storage.presigned_get_url(key, PRESIGN_TTL_SECONDS) if key else None

        # A 600 px source has no larger form; the next size down stands in, so
        # a lightbox never asks for a file that is not there.
        preview = at(PREVIEW_SIDE)
        medium = at(MEDIUM_SIDE) or preview
        large = at(LARGE_SIDE) or medium
        return CoinImage(preview=preview, medium=medium, large=large, attribution=media.attribution)

    def pick_catalog_images(self, files: list[MediaFile]) -> CatalogImages:
        """Files must already be filtered to what the viewer may see."""
        best: dict[MediaRole, MediaFile] = {}
        for media in files:
            current = best.get(media.role)
            if current is None or self._ranking(media) < self._ranking(current):
                best[media.role] = media

        obverse = best.get(MediaRole.OBVERSE)
        reverse = best.get(MediaRole.REVERSE)
        thumbnail_source = obverse or reverse
        return CatalogImages(
            obverse=self.image_of(obverse) if obverse else None,
            reverse=self.image_of(reverse) if reverse else None,
            thumbnail_url=self.thumbnail_url(thumbnail_source) if thumbnail_source else None,
        )

    @staticmethod
    def _ranking(media: MediaFile) -> tuple[int, int]:
        # Lower is better; among equals the newest row wins.
        return (_SOURCE_PRIORITY.get(media.source, 3), -media.id)
