"""Classic (non-ML) white-background removal for round coin photos.

Only a genuinely white background and a genuinely round object are cut; a
blister pack, a colored backdrop or a coin that touches the frame is left
alone. See docs/06-media-storage.md, "Удаление фона", for the rule and the
runbook. Pillow plus stdlib only, no opencv/rembg/numpy.

`classify` decides; `cut_background` executes the decision, then trims the
result to its alpha bbox with `trim_to_alpha` so every cut coin fills its
frame at the same visible size regardless of the source photo's margins.
All three take and return Pillow images so the same functions serve the
batch script (backend/scripts/remove_photo_backgrounds.py) and the ingest
path (app.core.images.process_image).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageStat

# "Almost white": every channel at least this bright, and close enough to
# each other that a pale tint (cream, light gray-blue) does not pass as a
# white background.
CORNER_WHITE_MIN = 235
CORNER_CHANNEL_SPREAD_MAX = 12
CORNER_SAMPLE_PX = 12

# The flood fill grows from the border while a pixel stays within this
# distance (per channel) of the sampled background color -- wide enough for
# a mild vignette or JPEG noise, narrow enough to stop at a metal coin edge.
FLOOD_TOLERANCE = 28

# Classification runs on a shrunk copy: a pure-Python flood fill over a
# 1200x1200 source is slow, and a coin's silhouette does not need per-pixel
# resolution to be classified. The resulting mask is scaled back up (and
# feathered in cut_background) before it ever touches the full image.
CLASSIFY_MAX_SIDE = 400

# A component smaller than this fraction of the frame is a fleck of shadow
# or compression noise, not a second object -- dropped rather than counted
# against "one connected component".
NOISE_AREA_FRACTION = 0.0008

# The background must reach at least this fraction of the frame's own
# border pixels; an object cut off by the edge cannot be a whole coin.
BORDER_BACKGROUND_MIN = 0.97

# Circularity = object area / its own bounding-box area. A disc is ~0.785,
# a square 1.0 -- the upper bound is what actually screens out rectangular
# blister packs, the lower bound catches shapes too irregular to be a coin.
CIRCULARITY_MAX = 0.87
CIRCULARITY_MIN = 0.60

# Edge softening on the final mask so the cut does not look scissored.
FEATHER_RADIUS = 1.4

# Bbox threshold for trim_to_alpha: low enough to keep the feathered rim
# cut_background leaves (see FEATHER_RADIUS) inside the crop, high enough to
# ignore stray near-zero alpha noise at the very edge of the frame.
TRIM_ALPHA_THRESHOLD = 8

# Padding added around that bbox, as a fraction of its own larger side, so
# the coin does not end up touching the frame exactly.
TRIM_PADDING_FRACTION = 0.02
TRIM_PADDING_MIN_PX = 2


@dataclass(frozen=True, slots=True)
class Verdict:
    """A classification outcome; `mask` and `metrics` are set only when `cut`."""

    cut: bool
    reason: str | None
    mask: Image.Image | None = None  # mode "L", same size as the input image
    metrics: dict[str, float] | None = None


@dataclass(slots=True)
class _Component:
    area: int
    bbox: tuple[int, int, int, int]
    pixels: list[tuple[int, int]]


def classify(img: Image.Image) -> Verdict:
    """Decide whether `img` is a coin on a white background worth cutting."""
    rgb = img.convert("RGB")
    if not _corners_are_white(rgb):
        return Verdict(cut=False, reason="skip:not_white_bg")

    scale = min(1.0, CLASSIFY_MAX_SIDE / max(rgb.size))
    small = (
        rgb
        if scale == 1.0
        else rgb.resize(
            (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
            Image.Resampling.BILINEAR,
        )
    )
    background = _flood_fill_background(small, _sample_background_color(small))

    border_fraction = _border_background_fraction(background, small.size)
    if border_fraction < BORDER_BACKGROUND_MIN:
        return Verdict(cut=False, reason="skip:object_touches_border")

    frame_area = small.width * small.height
    components = [
        component
        for component in _object_components(background, small.size)
        if component.area >= NOISE_AREA_FRACTION * frame_area
    ]
    if len(components) != 1:
        return Verdict(cut=False, reason="skip:fragments")

    component = components[0]
    x0, y0, x1, y1 = component.bbox
    bbox_area = (x1 - x0 + 1) * (y1 - y0 + 1)
    circularity = component.area / bbox_area if bbox_area else 0.0
    if circularity > CIRCULARITY_MAX:
        return Verdict(cut=False, reason="skip:not_round")
    if circularity < CIRCULARITY_MIN:
        return Verdict(cut=False, reason="skip:odd_shape")

    small_mask = _component_mask(component, small.size)
    mask = small_mask if scale == 1.0 else small_mask.resize(rgb.size, Image.Resampling.BILINEAR)
    metrics = {"borderBackgroundFraction": border_fraction, "circularity": circularity}
    return Verdict(cut=True, reason=None, mask=mask, metrics=metrics)


def cut_background(img: Image.Image, mask: Image.Image) -> Image.Image:
    """RGBA copy of `img` with `mask` (255 = object) as alpha, edges feathered.

    Trimmed to the alpha bbox as a last step: source photos carry wildly
    different empty margins around the coin, and leaving them in the frame is
    what made cut coins render at different visible sizes in a grid of tiles.
    """
    if mask.size != img.size:
        mask = mask.resize(img.size, Image.Resampling.BILINEAR)
    feathered = mask.filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))
    rgba = img.convert("RGBA")
    rgba.putalpha(feathered)
    return trim_to_alpha(rgba)


def trim_to_alpha(img: Image.Image, padding_fraction: float = TRIM_PADDING_FRACTION) -> Image.Image:
    """Crop `img` to its non-transparent bbox, plus a uniform padding.

    The bbox is taken at TRIM_ALPHA_THRESHOLD, not at fully opaque, so the
    feathered rim `cut_background` leaves is never clipped. Padding is a
    fraction of the bbox's own larger side (floored at TRIM_PADDING_MIN_PX)
    and never pushes the crop past the original frame. An image with nothing
    above the threshold has no object to crop to and is returned unchanged.
    """
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    alpha_mask = rgba.split()[3].point(lambda a: 255 if a > TRIM_ALPHA_THRESHOLD else 0)
    bbox = alpha_mask.getbbox()
    if bbox is None:
        return img

    x0, y0, x1, y1 = bbox
    padding = max(TRIM_PADDING_MIN_PX, round(padding_fraction * max(x1 - x0, y1 - y0)))
    width, height = img.size
    crop_box = (
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(width, x1 + padding),
        min(height, y1 + padding),
    )
    return img.crop(crop_box)


def _corner_boxes(img: Image.Image) -> list[tuple[int, int, int, int]]:
    width, height = img.size
    side = max(1, min(CORNER_SAMPLE_PX, width // 2, height // 2))
    return [
        (0, 0, side, side),
        (width - side, 0, width, side),
        (0, height - side, side, height),
        (width - side, height - side, width, height),
    ]


def _average_color(patch: Image.Image) -> tuple[float, float, float]:
    r, g, b = ImageStat.Stat(patch).mean
    return r, g, b


def _corners_are_white(img: Image.Image) -> bool:
    for box in _corner_boxes(img):
        r, g, b = _average_color(img.crop(box))
        if min(r, g, b) < CORNER_WHITE_MIN:
            return False
        if max(r, g, b) - min(r, g, b) > CORNER_CHANNEL_SPREAD_MAX:
            return False
    return True


def _sample_background_color(img: Image.Image) -> tuple[float, float, float]:
    corners = [_average_color(img.crop(box)) for box in _corner_boxes(img)]
    return (
        sum(c[0] for c in corners) / len(corners),
        sum(c[1] for c in corners) / len(corners),
        sum(c[2] for c in corners) / len(corners),
    )


def _flood_fill_background(img: Image.Image, bg: tuple[float, float, float]) -> bytearray:
    """1 = background, reached from the border within FLOOD_TOLERANCE; 0 = object."""
    width, height = img.size
    pixels = img.load()
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def is_background(x: int, y: int) -> bool:
        r, g, b = pixels[x, y]  # type: ignore[index, misc]
        return bool(
            abs(r - bg[0]) <= FLOOD_TOLERANCE
            and abs(g - bg[1]) <= FLOOD_TOLERANCE
            and abs(b - bg[2]) <= FLOOD_TOLERANCE
        )

    def seed(x: int, y: int) -> None:
        idx = y * width + x
        if not visited[idx] and is_background(x, y):
            visited[idx] = 1
            queue.append((x, y))

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                idx = ny * width + nx
                if not visited[idx] and is_background(nx, ny):
                    visited[idx] = 1
                    queue.append((nx, ny))
    return visited


def _border_pixels(size: tuple[int, int]) -> set[tuple[int, int]]:
    width, height = size
    coords = {(x, 0) for x in range(width)} | {(x, height - 1) for x in range(width)}
    coords |= {(0, y) for y in range(height)} | {(width - 1, y) for y in range(height)}
    return coords


def _border_background_fraction(visited: bytearray, size: tuple[int, int]) -> float:
    width, _ = size
    border = _border_pixels(size)
    if not border:
        return 1.0
    background = sum(1 for x, y in border if visited[y * width + x])
    return background / len(border)


def _object_components(visited: bytearray, size: tuple[int, int]) -> list[_Component]:
    width, height = size
    labeled = bytearray(width * height)
    components: list[_Component] = []
    for start_y in range(height):
        for start_x in range(width):
            start_idx = start_y * width + start_x
            if visited[start_idx] or labeled[start_idx]:
                continue
            labeled[start_idx] = 1
            pixels: list[tuple[int, int]] = []
            queue: deque[tuple[int, int]] = deque([(start_x, start_y)])
            min_x = max_x = start_x
            min_y = max_y = start_y
            while queue:
                x, y = queue.popleft()
                pixels.append((x, y))
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        nidx = ny * width + nx
                        if not visited[nidx] and not labeled[nidx]:
                            labeled[nidx] = 1
                            queue.append((nx, ny))
            components.append(
                _Component(area=len(pixels), bbox=(min_x, min_y, max_x, max_y), pixels=pixels)
            )
    return components


def _component_mask(component: _Component, size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    pixels = mask.load()
    for x, y in component.pixels:
        pixels[x, y] = 255  # type: ignore[index]
    return mask
