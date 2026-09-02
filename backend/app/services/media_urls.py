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
from app.core.storage import ObjectStorage, build_s3_client
from app.models import MediaFile
from app.models.enums import MediaRole, MediaSource

PRESIGN_TTL_SECONDS = 3600

_SOURCE_PRIORITY = {
    MediaSource.USER_UPLOAD: 0,
    MediaSource.NBU: 1,
    MediaSource.MANUAL: 1,
    MediaSource.UCOIN: 2,
}


@dataclass
class CatalogImages:
    obverse_url: str | None = None
    reverse_url: str | None = None
    thumbnail_url: str | None = None


@lru_cache
def _storage() -> ObjectStorage:
    settings = get_settings()
    return ObjectStorage(build_s3_client(settings), settings.s3_bucket)


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
            obverse_url=self.file_url(obverse) if obverse else None,
            reverse_url=self.file_url(reverse) if reverse else None,
            thumbnail_url=self.thumbnail_url(thumbnail_source) if thumbnail_source else None,
        )

    @staticmethod
    def _ranking(media: MediaFile) -> tuple[int, int]:
        # Lower is better; among equals the newest row wins.
        return (_SOURCE_PRIORITY.get(media.source, 3), -media.id)
