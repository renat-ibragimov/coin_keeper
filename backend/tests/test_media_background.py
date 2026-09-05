"""app.services.media_background: synthetic images with a known right answer.

Each test builds the shape by hand with PIL so the expected verdict is not a
guess -- a circle on white must cut, a rectangle on white must fail on
roundness alone, a circle on a colored background must fail before any shape
work happens, and a circle touching the frame must fail on containment.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from app.services.media_background import classify

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
