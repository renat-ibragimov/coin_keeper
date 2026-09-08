"""Tell a clean coin photograph from a packaging one (roll, tube, box).

A coin shot is one round object on a plain background; packaging is anything
else. The check is geometric, not learned: find the foreground against the
background sampled from the borders, take the dominant contours, and measure
how circular they are. An image passes as a coin photo when every significant
object in it is a circle (one side, or obverse+reverse laid side by side).

This is a ranking, not a gate. `pick_best` takes a page's images in page
order and returns the best-looking ones; when nothing on the page passes as
a coin, it falls back to the first images exactly as a parser without this
module would, and only marks the choice as a fallback. The result can never
be worse than taking the page head — only sometimes better.

Usage:
    python classify_coin_photos.py IMAGE [IMAGE ...]
    python classify_coin_photos.py --move-rejected DIR IMAGE ...
    python classify_coin_photos.py --pick 2 IMAGE [IMAGE ...]

Exit code 0 always; verdicts are printed per file, `--pick` prints the chosen
files last, so the caller can grep or parse.
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# An object must be at least this share of the frame to be judged at all;
# smaller blobs are logos, shadows and dust.
MIN_AREA_SHARE = 0.02
# 4 * pi * area / perimeter^2: 1.0 is a perfect circle. Embossed rims and
# JPEG halos eat a little, so the bar is below 1.
MIN_CIRCULARITY = 0.82
# Width to height of the bounding box; a coin is square-ish even tilted.
MIN_ASPECT = 0.85
# How much of the minimal enclosing circle the object fills; a coin fills
# nearly all of it, a tube standing upright fills a stripe.
MIN_CIRCLE_FILL = 0.80
# Foreground/background split: distance from the border colour, 0..255.
BACKGROUND_TOLERANCE = 28


@dataclass
class Verdict:
    is_coin: bool
    objects: int
    worst_circularity: float
    worst_aspect: float
    worst_fill: float
    reason: str


def _foreground_mask(image: np.ndarray) -> np.ndarray:
    """Everything that is not the border colour.

    The background colour is read off the frame's own borders rather than
    assumed white: NBU shots are white, ua-coins are near-white, and a grey
    studio background should work the same way.
    """
    border = np.concatenate([image[0, :], image[-1, :], image[:, 0], image[:, -1]]).astype(
        np.float32
    )
    background = np.median(border, axis=0)
    distance = np.linalg.norm(image.astype(np.float32) - background, axis=2)
    mask = (distance > BACKGROUND_TOLERANCE).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def classify(path: Path, max_side: int = 800) -> Verdict:
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        return Verdict(False, 0, 0.0, 0.0, 0.0, "unreadable")
    # A transparent PNG hands us the mask for free: the alpha channel *is*
    # the foreground, cut by whoever prepared the image.
    if raw.ndim == 3 and raw.shape[2] == 4:
        alpha = raw[:, :, 3]
        image = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        premask = (alpha > 16).astype(np.uint8) * 255
    else:
        image = raw if raw.ndim == 3 else cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
        premask = None

    scale = max_side / max(image.shape[:2])
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if premask is not None:
            premask = cv2.resize(  # type: ignore[assignment]
                premask, image.shape[1::-1], interpolation=cv2.INTER_NEAREST
            )

    mask = premask if premask is not None else _foreground_mask(image)
    frame_area = mask.shape[0] * mask.shape[1]
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    significant = [c for c in contours if cv2.contourArea(c) >= frame_area * MIN_AREA_SHARE]
    if not significant:
        return Verdict(False, 0, 0.0, 0.0, 0.0, "no object found")

    worst_circularity, worst_aspect, worst_fill = 1.0, 1.0, 1.0
    for contour in significant:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, closed=True)
        circularity = 4 * math.pi * area / (perimeter * perimeter) if perimeter else 0.0
        _x, _y, w, h = cv2.boundingRect(contour)
        aspect = min(w, h) / max(w, h)
        (_, _), radius = cv2.minEnclosingCircle(contour)
        fill = area / (math.pi * radius * radius) if radius else 0.0
        worst_circularity = min(worst_circularity, circularity)
        worst_aspect = min(worst_aspect, aspect)
        worst_fill = min(worst_fill, fill)

    is_coin = (
        worst_circularity >= MIN_CIRCULARITY
        and worst_aspect >= MIN_ASPECT
        and worst_fill >= MIN_CIRCLE_FILL
    )
    reason = "ok" if is_coin else "non-circular object in frame"
    return Verdict(is_coin, len(significant), worst_circularity, worst_aspect, worst_fill, reason)


def combine(verdicts: list[Verdict]) -> Verdict:
    """The worst of several verdicts, as one — a record with several stored
    sides is only as good as its worst side (scripts/scan_coin_photo_packaging.py,
    app/ukraine_pipeline/photo_upgrade.py)."""
    if not verdicts:
        return Verdict(False, 0, 0.0, 0.0, 0.0, "no photo")
    is_coin = all(v.is_coin for v in verdicts)
    circularity = min(v.worst_circularity for v in verdicts)
    aspect = min(v.worst_aspect for v in verdicts)
    fill = min(v.worst_fill for v in verdicts)
    objects = sum(v.objects for v in verdicts)
    reason = "ok" if is_coin else "non-circular object in frame"
    return Verdict(is_coin, objects, circularity, aspect, fill, reason)


def score(verdict: Verdict) -> float:
    """One continuous number for ranking; the pass/fail bar stays separate.

    Circularity carries the most weight because it separates best (see the
    synthetic table in the commit message); fill catches upright tubes,
    aspect catches lying rolls.
    """
    return 0.5 * verdict.worst_circularity + 0.3 * verdict.worst_fill + 0.2 * verdict.worst_aspect


@dataclass
class Pick:
    chosen: list[Path]
    fallback: bool
    scores: dict[Path, float]


def pick_best(paths: list[Path], count: int = 2) -> Pick:
    """The best `count` images of a page, in page order among equals.

    Every image that classifies as a coin beats every one that does not;
    within each group the score decides and the page order breaks ties, so a
    page of nothing but packaging returns exactly its first images — the
    same choice a parser without this module makes — flagged as a fallback.
    """
    verdicts = {path: classify(path) for path in paths}
    scores = {path: score(verdicts[path]) for path in paths}
    ranked = sorted(
        paths,
        key=lambda p: (not verdicts[p].is_coin, -scores[p], paths.index(p)),
    )
    chosen = ranked[:count]
    fallback = not any(verdicts[p].is_coin for p in chosen)
    if fallback:
        chosen = paths[:count]
    return Pick(chosen=chosen, fallback=fallback, scores=scores)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument(
        "--move-rejected",
        type=Path,
        default=None,
        help="move packaging shots into this directory instead of only reporting",
    )
    parser.add_argument(
        "--pick",
        type=int,
        default=None,
        metavar="N",
        help="rank the given images as one page and print the N chosen ones",
    )
    args = parser.parse_args()
    if args.pick:
        pick = pick_best(args.images, args.pick)
        for path in args.images:
            marker = "*" if path in pick.chosen else " "
            print(f"{marker} {pick.scores[path]:.2f}  {path.name}")
        suffix = "  (fallback: page head, nothing passed)" if pick.fallback else ""
        print("chosen: " + " ".join(p.name for p in pick.chosen) + suffix)
        return 0
    if args.move_rejected:
        args.move_rejected.mkdir(parents=True, exist_ok=True)
    for path in args.images:
        verdict = classify(path)
        label = "coin" if verdict.is_coin else "packaging"
        print(
            f"{label:9s} {path.name}  objects={verdict.objects}"
            f" circ={verdict.worst_circularity:.2f} aspect={verdict.worst_aspect:.2f}"
            f" fill={verdict.worst_fill:.2f} ({verdict.reason})"
        )
        if not verdict.is_coin and args.move_rejected:
            shutil.move(str(path), args.move_rejected / path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
