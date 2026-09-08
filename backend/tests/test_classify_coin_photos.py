"""classify_coin_photos: a coin (one circle on a plain background) versus
packaging (a roll, a tube, a blister — anything not round).

Every image here is synthetic (drawn with Pillow, this project's own image
dependency) rather than a real catalog photo: real photos are not committed
to the repository (CLAUDE.md), and a plain circle/rectangle is enough to
exercise the geometry the classifier actually measures — circularity,
bounding-box aspect, and fill of the minimal enclosing circle.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.ukraine_pipeline.classify_coin_photos import classify, pick_best

BACKGROUND = (245, 245, 245)
COIN_COLOR = (150, 120, 70)


def _save(image: Image.Image, path: Path) -> Path:
    image.save(path)
    return path


def coin_image(path: Path, *, size: int = 300, diameter: int = 220) -> Path:
    """One round coin, centered, well clear of the frame edge."""
    image = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    margin = (size - diameter) // 2
    draw.ellipse((margin, margin, margin + diameter, margin + diameter), fill=COIN_COLOR)
    return _save(image, path)


def upright_tube_image(path: Path, *, size: int = 300) -> Path:
    """A roll standing on end: tall, narrow — fails the aspect check."""
    image = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((size * 0.35, size * 0.1, size * 0.65, size * 0.9), fill=COIN_COLOR)
    return _save(image, path)


def lying_roll_image(path: Path, *, size: int = 300) -> Path:
    """A roll lying on its side: wide, short — also fails the aspect check."""
    image = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((size * 0.1, size * 0.35, size * 0.9, size * 0.65), fill=COIN_COLOR)
    return _save(image, path)


def blank_image(path: Path, *, size: int = 300) -> Path:
    """Nothing but the background — no object at all."""
    return _save(Image.new("RGB", (size, size), BACKGROUND), path)


def coin_alpha_image(path: Path, *, size: int = 300, diameter: int = 220) -> Path:
    """A pre-cut PNG: the coin's own circle in the alpha channel, nothing
    else — classify() must read the mask off the alpha, not the pixels."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = (size - diameter) // 2
    draw.ellipse((margin, margin, margin + diameter, margin + diameter), fill=(*COIN_COLOR, 255))
    return _save(image, path)


def test_a_round_coin_passes(tmp_path: Path) -> None:
    verdict = classify(coin_image(tmp_path / "coin.jpg"))
    assert verdict.is_coin is True
    assert verdict.objects == 1
    assert verdict.reason == "ok"


def test_an_upright_tube_fails_on_aspect(tmp_path: Path) -> None:
    verdict = classify(upright_tube_image(tmp_path / "tube.jpg"))
    assert verdict.is_coin is False
    assert verdict.worst_aspect < 0.85


def test_a_lying_roll_fails_on_aspect(tmp_path: Path) -> None:
    verdict = classify(lying_roll_image(tmp_path / "roll.jpg"))
    assert verdict.is_coin is False
    assert verdict.worst_aspect < 0.85


def test_a_blank_frame_finds_no_object(tmp_path: Path) -> None:
    verdict = classify(blank_image(tmp_path / "blank.jpg"))
    assert verdict.is_coin is False
    assert verdict.objects == 0
    assert verdict.reason == "no object found"


def test_an_unreadable_path_is_reported_not_raised(tmp_path: Path) -> None:
    verdict = classify(tmp_path / "does-not-exist.jpg")
    assert verdict.is_coin is False
    assert verdict.reason == "unreadable"


def test_alpha_channel_is_used_as_a_ready_made_mask(tmp_path: Path) -> None:
    verdict = classify(coin_alpha_image(tmp_path / "coin.png"))
    assert verdict.is_coin is True


def test_pick_best_prefers_the_coin_over_packaging(tmp_path: Path) -> None:
    paths = [
        upright_tube_image(tmp_path / "1.jpg"),
        coin_image(tmp_path / "2.jpg"),
        lying_roll_image(tmp_path / "3.jpg"),
    ]
    pick = pick_best(paths, count=1)
    assert pick.chosen == [paths[1]]
    assert pick.fallback is False


def test_pick_best_falls_back_to_page_order_when_nothing_passes(tmp_path: Path) -> None:
    paths = [
        upright_tube_image(tmp_path / "1.jpg"),
        lying_roll_image(tmp_path / "2.jpg"),
        lying_roll_image(tmp_path / "3.jpg"),
    ]
    pick = pick_best(paths, count=2)
    assert pick.chosen == paths[:2]
    assert pick.fallback is True
