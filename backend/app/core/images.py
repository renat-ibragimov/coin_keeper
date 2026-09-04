"""Image processing rules from docs/06-media-storage.md.

Three sizes, one format. A listing shows a coin at about 150 px, a card at
about 300, and the lightbox as large as the screen allows; serving one file for
all three either wastes bandwidth or blurs the lightbox. So every image is
stored as 300, 600 and 1200 px WebP at quality 80, and the page picks with
srcset.

The source file is not kept. Coins are round and small, 1200 px is past the
point where more resolution shows more coin, and the National Bank's 1600 px
PNGs are about four megabytes each.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Final

from PIL import Image, UnidentifiedImageError

MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_SIDE = 4000
QUALITY = 80
PREVIEW_SIDE: Final = 300
MEDIUM_SIDE: Final = 600
LARGE_SIDE: Final = 1200
VARIANT_SIDES: Final = (PREVIEW_SIDE, MEDIUM_SIDE, LARGE_SIDE)
ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


class ImageRejectedError(Exception):
    """The payload is not an image we are willing to store."""


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    """The same picture at every stored size, plus what the row records."""

    variants: dict[int, bytes]
    width: int
    height: int
    size_bytes: int
    sha256: str
    mime_type: str = "image/webp"

    @property
    def largest(self) -> bytes:
        return self.variants[max(self.variants)]

    @property
    def preview(self) -> bytes:
        return self.variants[PREVIEW_SIDE]

    @property
    def total_bytes(self) -> int:
        return sum(len(payload) for payload in self.variants.values())

    def processed_sides(self) -> tuple[int, ...]:
        """The sizes that came out — a small source yields fewer than three."""
        return tuple(sorted(self.variants))


def process_image(payload: bytes) -> ProcessedImage:
    """Validate, strip metadata and encode every stored size.

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

        variants: dict[int, bytes] = {}
        width = height = 0
        seen: set[tuple[int, int]] = set()
        for side in VARIANT_SIDES:
            resized = stripped.copy()
            # thumbnail() only ever shrinks: a source smaller than the box is
            # stored at its own size rather than blown up.
            resized.thumbnail((side, side), Image.Resampling.LANCZOS)
            if resized.size in seen:
                # A 600 px source would otherwise be stored twice, once as
                # "600" and once as an identical "1200".
                continue
            seen.add(resized.size)
            variants[side] = _encode(resized)
            width, height = resized.size

    return ProcessedImage(
        variants=variants,
        width=width,
        height=height,
        size_bytes=len(variants[max(variants)]),
        # Of the source, not of our encoding: it identifies the file upstream
        # and is what tells a second run that nothing has changed.
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=QUALITY, method=4)
    return buffer.getvalue()
