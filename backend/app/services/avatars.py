"""Storing and serving the account's profile picture (users.avatar_key).

Deliberately outside the `media_files` machinery: that table's CHECK ties
every file to a catalog or collection item, and its source/role columns answer
questions a face does not raise. One column, one key, one size — see migration
0020 and docs/media.md for the key layout.

`user_out` is the single place a UserOut is built, so every response that
carries a user carries the signed avatar URL with it. A second hand-rolled
`UserOut.model_validate(...)` somewhere else is how half the endpoints would
quietly start answering without a picture.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

import anyio.to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.images import process_avatar
from app.core.media_keys import avatar_key
from app.core.storage import ObjectStorage, build_s3_client
from app.models import User
from app.schemas.auth import UserOut

PRESIGN_TTL_SECONDS = 3600
CONTENT_TYPE = "image/webp"
# Of the source, not of our encoding: what identifies the picture the person
# picked. Twelve hex characters are plenty to separate one person's successive
# avatars, which is all the name has to do.
KEY_DIGEST_CHARS = 12


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


def avatar_url_of(user: User) -> str | None:
    if not user.avatar_key:
        return None
    return _storage().presigned_get_url(user.avatar_key, PRESIGN_TTL_SECONDS)


def user_out(user: User) -> UserOut:
    """The one way a User becomes a UserOut."""
    return UserOut.model_validate(user).model_copy(update={"avatar_url": avatar_url_of(user)})


class AvatarService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage | None = None) -> None:
        self._session = session
        self._storage = storage or _storage()

    async def set_avatar(self, *, user: User, payload: bytes) -> User:
        """Store the picture and point the row at it.

        Raises ImageRejectedError for anything that is not an image we accept.

        The order matters: write the new object, point the row at it, and only
        then drop the old one. A failure part-way through leaves either the
        previous picture or a file nobody references — never a row naming a
        key that is not in the bucket, which is the one state the interface
        cannot render.
        """
        # Pillow decodes, crops and re-encodes on the calling thread, which
        # here is the event loop — a 4000 px source would hold up every other
        # request for the duration. Off to a worker thread it goes.
        encoded = await anyio.to_thread.run_sync(process_avatar, payload)
        digest = hashlib.sha256(payload).hexdigest()[:KEY_DIGEST_CHARS]
        key = avatar_key(user.id, digest)
        previous = user.avatar_key

        self._storage.put(key, encoded, CONTENT_TYPE)
        user.avatar_key = key
        await self._session.flush()

        if previous and previous != key:
            self._storage.delete_many([previous])
        return user

    async def remove_avatar(self, *, user: User) -> User:
        """Clear the row first, then the bucket; deleting nothing is not an error."""
        previous = user.avatar_key
        user.avatar_key = None
        await self._session.flush()
        if previous:
            self._storage.delete_many([previous])
        return user


__all__ = ["AvatarService", "avatar_url_of", "user_out"]
