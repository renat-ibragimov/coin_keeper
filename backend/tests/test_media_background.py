"""app.services.media_background: synthetic images with a known right answer.

Each test builds the shape by hand with PIL so the expected verdict is not a
guess -- a circle on white must cut, a rectangle on white must fail on
roundness alone, a circle on a colored background must fail before any shape
work happens, and a circle touching the frame must fail on containment.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from app.services.media_background import classify, cut_background, trim_to_alpha

SIZE = 240
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)
COIN = (150, 120, 40)


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


def test_circle_touching_the_border_is_rejected() -> None:
    img = _canvas()
    draw = ImageDraw.Draw(img)
    # Wide enough to reach past the left and right edges of the frame.
    draw.ellipse((-20, SIZE // 4, SIZE + 20, SIZE - SIZE // 4), fill=COIN)

    verdict = classify(img)

    assert not verdict.cut
    assert verdict.reason == "skip:object_touches_border"


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
