"""Image processing rules from docs/media.md.

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

from app.services.media_background import classify, cut_background

MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_SIDE = 4000
QUALITY = 80
PREVIEW_SIDE: Final = 300
MEDIUM_SIDE: Final = 600
LARGE_SIDE: Final = 1200
VARIANT_SIDES: Final = (PREVIEW_SIDE, MEDIUM_SIDE, LARGE_SIDE)
# A profile picture is shown at 26-40 css px and nowhere else, so one size is
# enough; 256 still covers a 3x display without asking the browser to scale up.
AVATAR_SIDE: Final = 256
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


def process_image(payload: bytes, *, remove_background: bool = True) -> ProcessedImage:
    """Validate, strip metadata, cut a white round background and encode every size.

    Raises ImageRejectedError for anything that is not an acceptable image;
    callers decide whether that is fatal or just a skipped row.

    `remove_background` is the one point every ingest path (the Ukrainian
    photo pipeline, and any future upload endpoint) shares, so a white,
    round coin photo is cut to a transparent WebP as it comes in rather than
    needing a separate pass later — see app.services.media_background and
    docs/media.md, "Удаление фона". A migration or other special
    path that must keep bytes exactly as given can pass False.
    """
    stripped = _validated_stripped(payload)

    # Already-transparent input (a manual upload, say) is left as it is;
    # only an opaque source is a candidate for the white-background cut.
    if remove_background and stripped.mode == "RGB":
        verdict = classify(stripped)
        if verdict.cut and verdict.mask is not None:
            stripped = cut_background(stripped, verdict.mask)

    # Of the source, not of our encoding: it identifies the file upstream
    # and is what tells a second run that nothing has changed.
    return encode_variants(stripped, sha256=hashlib.sha256(payload).hexdigest())


def process_avatar(payload: bytes) -> bytes:
    """One square WebP for a profile picture (users.avatar_key).

    No background cut: `classify`/`cut_background` are tuned for a coin shot
    against white paper and would happily eat the wall behind a person.

    The centre crop repeats what the browser's cropper already did. It has to:
    the endpoint takes raw bytes from whoever calls it, and a client that is
    not our cropper must still not be able to store a picture that is not
    square.
    """
    image = _validated_stripped(payload)
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    square = image.crop((left, top, left + side, top + side))
    # thumbnail() only shrinks, so a source smaller than 256 keeps its size
    # rather than being blown up into a blurry square.
    square.thumbnail((AVATAR_SIDE, AVATAR_SIDE), Image.Resampling.LANCZOS)
    return _encode(square)


def _validated_stripped(payload: bytes) -> Image.Image:
    """Everything that must happen to any payload before we keep it.

    The size limits, the verify-by-content check and the metadata strip are
    the same whether the picture becomes a coin's three variants or somebody's
    avatar; only what happens afterwards differs.
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
        # where Pillow keeps EXIF and ICC data, is left behind. The copy also
        # outlives the `with`, which the opened source would not.
        converted = source.convert("RGBA" if source.mode == "RGBA" else "RGB")
        stripped = Image.new(converted.mode, converted.size)
        stripped.paste(converted)
        return stripped


def encode_variants(image: Image.Image, *, sha256: str) -> ProcessedImage:
    """Resize an already-decoded, already-decided image to every stored size.

    Shared by process_image above and by the batch background-removal step
    (backend/scripts/remove_photo_backgrounds.py), which starts from a
    stored variant rather than a freshly downloaded payload and so has
    nothing left to validate — only sizes left to produce.
    """
    variants: dict[int, bytes] = {}
    width = height = 0
    seen: set[tuple[int, int]] = set()
    for side in VARIANT_SIDES:
        resized = image.copy()
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
        sha256=sha256,
    )


def _encode(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=QUALITY, method=4)
    return buffer.getvalue()
