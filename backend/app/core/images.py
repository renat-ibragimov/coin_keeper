"""Image processing rules from docs/06-media-storage.md.

The original is not kept as uploaded: coins are round and small, 1600 px on the
long side is plenty, and the saving is substantial.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_SIDE = 4000
ORIGINAL_MAX_SIDE = 1600
ORIGINAL_QUALITY = 85
THUMBNAIL_SIDE = 300
THUMBNAIL_QUALITY = 80
ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class ImageRejectedError(Exception):
    """The payload is not an image we are willing to store."""


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    original: bytes
    thumbnail: bytes
    width: int
    height: int
    size_bytes: int
    sha256: str
    mime_type: str = "image/webp"


def process_image(payload: bytes) -> ProcessedImage:
    """Validate, normalise to WebP and build a thumbnail.

    Raises ImageRejectedError for anything that is not an acceptable image;
    callers decide whether that is fatal or just a skipped row.
    """
    if len(payload) > MAX_SOURCE_BYTES:
        msg = f"larger than {MAX_SOURCE_BYTES} bytes"
        raise ImageRejectedError(msg)

    try:
        # Verified by content, not by file extension.
        with Image.open(io.BytesIO(payload)) as probe:
            image_format = probe.format
            probe.verify()
    except (UnidentifiedImageError, OSError) as exc:
        msg = "not a readable image"
        raise ImageRejectedError(msg) from exc

    if image_format not in ACCEPTED_FORMATS:
        msg = f"unsupported format {image_format}"
        raise ImageRejectedError(msg)

    # verify() leaves the file unusable, so reopen for the actual work.
    with Image.open(io.BytesIO(payload)) as source:
        if max(source.size) > MAX_SOURCE_SIDE:
            msg = f"larger than {MAX_SOURCE_SIDE}px on a side"
            raise ImageRejectedError(msg)

        # Drop every scrap of metadata: EXIF carries geotags and camera data.
        # Pasting into a blank canvas copies pixels only — the `info` dict,
        # where Pillow keeps EXIF and ICC data, is left behind.
        converted = source.convert("RGBA" if source.mode == "RGBA" else "RGB")
        stripped = Image.new(converted.mode, converted.size)
        stripped.paste(converted)

        original = stripped.copy()
        original.thumbnail((ORIGINAL_MAX_SIDE, ORIGINAL_MAX_SIDE), Image.Resampling.LANCZOS)
        original_bytes = _encode(original, ORIGINAL_QUALITY)

        thumbnail = stripped.copy()
        # Fits inside the box without cropping.
        thumbnail.thumbnail((THUMBNAIL_SIDE, THUMBNAIL_SIDE), Image.Resampling.LANCZOS)
        thumbnail_bytes = _encode(thumbnail, THUMBNAIL_QUALITY)

        width, height = original.size

    return ProcessedImage(
        original=original_bytes,
        thumbnail=thumbnail_bytes,
        width=width,
        height=height,
        size_bytes=len(original_bytes),
        sha256=hashlib.sha256(original_bytes).hexdigest(),
    )


def _encode(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=4)
    return buffer.getvalue()
