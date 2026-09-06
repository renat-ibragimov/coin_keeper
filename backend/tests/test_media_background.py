"""app.services.media_background: synthetic images with a known right answer.

Each test builds the shape by hand with PIL so the expected verdict is not a
guess -- a circle on white must cut, a rectangle on white must fail on
roundness alone, a circle on a colored background must fail before any shape
work happens, and a circle touching the frame must fail on containment.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

from app.services.media_background import (
    BORDER_BACKGROUND_MIN,
    FLOOD_TOLERANCE_DARK,
    classify,
    cut_background,
    transparent_pixel_fraction,
    trim_to_alpha,
)

SIZE = 240
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)
COIN = (150, 120, 40)
DARK = (20, 20, 20)


def _canvas(background: tuple[int, int, int] = WHITE) -> Image.Image:
    return Image.new("RGB", (SIZE, SIZE), background)


def test_circle_on_white_is_cut() -> None:
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert verdict.cut
    assert verdict.reason is None
    assert verdict.mask is not None
    assert verdict.mask.size == img.size


def test_rectangle_on_white_is_not_round() -> None:
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.rectangle((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:not_round"


def test_circle_on_gray_is_not_white_background() -> None:
    img = _canvas(GRAY)
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:not_white_bg"


def test_border_mostly_covered_by_a_foreign_mark_is_rejected() -> None:
    """A well-formed round coin, but a border-hugging mark on all four edges.

    Stands in for heavy vignetting or a scanner/tray edge in the source photo:
    the round object itself is untouched, but the background no longer
    "embraces" the frame, and that must still fail before circularity is
    even considered.
    """
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)
    band, thickness = 190, 6
    x0 = (SIZE - band) // 2
    draw.rectangle((x0, 0, x0 + band, thickness), fill=COIN)
    draw.rectangle((x0, SIZE - thickness, x0 + band, SIZE), fill=COIN)
    draw.rectangle((0, x0, thickness, x0 + band), fill=COIN)
    draw.rectangle((SIZE - thickness, x0, SIZE, x0 + band), fill=COIN)

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:object_touches_border"
    assert verdict.metrics is not None
    assert verdict.metrics["borderBackgroundFraction"] < BORDER_BACKGROUND_MIN


def test_circle_clipped_by_one_edge_is_still_cut() -> None:
    """A coin cropped tight against one side of the frame: a single flat chord.

    This is the common ua-coins shape BORDER_BACKGROUND_MIN was relaxed for --
    the flood fill still seeds fine and the flat chord is already baked into
    the source photo, so it must not be rejected as object_touches_border.
    """
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin - 80, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert verdict.cut
    assert verdict.reason is None
    assert verdict.metrics is not None
    assert verdict.metrics["borderBackgroundFraction"] < 0.97  # would have failed the old cutoff


def test_circle_clipped_by_two_opposite_edges_is_not_round() -> None:
    """A coin cropped on both left and right, flattened into a near-rectangle.

    Losing two opposite chords pushes bbox fill past CIRCULARITY_MAX even
    though the border-background fraction alone would still pass -- this is
    what actually screens out a border-hugging blister pack now that touching
    one edge is allowed.
    """
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin - 100, margin, SIZE - margin + 100, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:not_round"
    assert verdict.metrics is not None
    assert verdict.metrics["borderBackgroundFraction"] >= BORDER_BACKGROUND_MIN


def test_circle_on_black_is_cut_dark() -> None:
    img = _canvas(DARK)
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert verdict.cut
    assert verdict.reason is None
    assert verdict.mask is not None
    assert verdict.metrics is not None
    assert verdict.metrics["bgKind"] == "dark"


def test_circle_on_white_is_still_plain_cut() -> None:
    """Regression guard: the white branch must not pick up a bgKind-related change."""
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert verdict.cut
    assert verdict.metrics is not None
    assert verdict.metrics["bgKind"] == "white"


def test_transparent_corners_over_a_black_matte_are_left_alone() -> None:
    """Regression guard for the 2026-09 incident (docs/06-media-storage.md).

    An RGBA source whose corners are transparent (alpha=0) over an arbitrary
    black matte must never reach the dark-background flood fill: its corners
    read exactly like a legitimate black-felt photo once alpha is discarded,
    and cutting it a second time would flood the matte and expose whatever it
    was hiding.
    """
    img = Image.new("RGBA", (SIZE, SIZE), (*DARK, 0))
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=(*COIN, 255))

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:already_transparent"
    assert verdict.mask is None


def test_opaque_circle_on_black_still_cuts_dark() -> None:
    """The dark branch itself must not regress: a genuinely opaque photo still cuts."""
    img = Image.new("RGBA", (SIZE, SIZE), (*DARK, 255))
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=(*COIN, 255))

    assert transparent_pixel_fraction(img) == 0.0

    verdict = classify(img)

    assert verdict.cut
    assert verdict.reason is None
    assert verdict.metrics is not None
    assert verdict.metrics["bgKind"] == "dark"


def test_dark_gray_uneven_background_is_skipped() -> None:
    """Mid-gray corners are neither white nor dark enough -- same skip as before."""
    img = _canvas((60, 60, 60))
    draw = ImageDraw.Draw(img)
    # Break corner uniformity so this cannot pass either the white or dark check.
    draw.rectangle((0, 0, 20, 20), fill=(95, 60, 60))
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:not_white_bg"


def test_dark_cut_keeps_a_mirror_field_ring_close_to_background() -> None:
    """A proof coin's rim reflects the black studio, staying close to the background color.

    The ring sits at exactly 2x FLOOD_TOLERANCE_DARK away from the sampled
    background -- clearly outside the dark branch's tight tolerance, so the
    flood fill must not swallow it into the background and clip the disc.
    """
    img = _canvas(DARK)
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    ring_width = 15
    ring_color = tuple(channel + 2 * FLOOD_TOLERANCE_DARK for channel in DARK)
    inner = margin + ring_width
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=ring_color)
    draw.ellipse((inner, inner, SIZE - inner, SIZE - inner), fill=COIN)

    verdict = classify(img)
    assert verdict.cut
    assert verdict.mask is not None

    # The mask must cover the full outer disc (including the ring), not just
    # the inner COIN-colored core -- comparing areas catches a swallowed ring
    # that a single circularity number would not (both are still circles).
    mask_area = sum(1 for value in verdict.mask.get_flattened_data() if value > 128)
    outer_radius = (SIZE - 2 * margin) / 2
    inner_radius = outer_radius - ring_width
    outer_area = math.pi * outer_radius**2
    inner_area = math.pi * inner_radius**2
    assert abs(mask_area - outer_area) < abs(mask_area - inner_area)


def test_cut_background_trims_wide_margins_to_the_coin() -> None:
    img = _canvas()
    draw = ImageDraw.Draw(img)
    margin = SIZE // 4
    draw.ellipse((margin, margin, SIZE - margin, SIZE - margin), fill=COIN)

    verdict = classify(img)
    assert verdict.mask is not None
    cut = cut_background(img, verdict.mask)

    assert cut.size[0] < SIZE
    assert cut.size[1] < SIZE
    assert cut.split()[3].getbbox() is not None


def test_trim_to_alpha_crops_wide_margins_with_padding() -> None:
    img = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((100, 100, 140, 140), fill=(*COIN, 255))

    trimmed = trim_to_alpha(img)

    bbox = img.split()[3].point(lambda a: 255 if a > 8 else 0).getbbox()
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    padding = max(2, round(0.02 * max(x1 - x0, y1 - y0)))
    expected = (
        min(x1 + padding, img.width) - max(x0 - padding, 0),
        min(y1 + padding, img.height) - max(y0 - padding, 0),
    )
    assert trimmed.size == expected


def test_trim_to_alpha_does_not_clip_the_feathered_edge() -> None:
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # A faint ring, well above the threshold, around a fully opaque core --
    # stands in for the soft edge cut_background's feathering leaves.
    draw.ellipse((60, 60, 140, 140), fill=(*COIN, 50))
    draw.ellipse((80, 80, 120, 120), fill=(*COIN, 255))

    original_above_threshold = sum(1 for a in img.split()[3].get_flattened_data() if a > 8)

    trimmed = trim_to_alpha(img)

    trimmed_above_threshold = sum(1 for a in trimmed.split()[3].get_flattened_data() if a > 8)
    assert trimmed_above_threshold == original_above_threshold


def test_trim_to_alpha_is_near_no_op_on_an_already_trimmed_image() -> None:
    img = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 20, 220, 220), fill=(*COIN, 255))

    once = trim_to_alpha(img)
    twice = trim_to_alpha(once)

    assert abs(once.width - twice.width) <= 2
    assert abs(once.height - twice.height) <= 2
