#!/usr/bin/env python3
"""Derive every brand asset from the two source logos.

Sources (the single source of truth, kept in git):
  public/brand/logo-full.src.png  — shield + BAKOST NUMISMATICS, transparent
  public/brand/logo-mark.src.png  — BN monogram on a coin, transparent

Outputs (also committed: they are site statics, regenerate with `npm run brand`):
  public/brand/logo-full-{400,800,1600}.{webp,png}
  public/brand/logo-mark-{128,256,512}.{webp,png}
  public/brand/favicon-32.png, apple-touch-icon.png (180, opaque),
  public/brand/icon-192.png, icon-512.png, icon-512-maskable.png (opaque, safe zone)
  public/favicon.ico (16 + 32 + 48)

Pillow only: it is already part of the backend toolchain, so no native npm
dependency is needed. Metadata is never copied — Pillow writes none unless asked.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent / "public"
BRAND = ROOT / "brand"

# Light theme tokens (frontend/src/shared/theme/tokens.css): --color-bg.
# Opaque icons (Apple, maskable) sit on the canonical paper background.
PAPER = (242, 236, 223, 255)

FULL_WIDTHS = (400, 800, 1600)
MARK_SIZES = (128, 256, 512)
# `exact=False` lets the encoder drop colour under fully transparent pixels;
# the full logo needs the lower quality to meet its byte budget, the mark
# is small enough to keep more detail.
WEBP_FULL = {"quality": 72, "method": 6}
WEBP_MARK = {"quality": 82, "method": 6}
PNG = {"optimize": True}

BUDGETS = {"logo-full-800.webp": 60 * 1024, "logo-mark-256.webp": 20 * 1024}


def load_trimmed(name: str) -> Image.Image:
    image = Image.open(BRAND / name).convert("RGBA")
    bbox = image.getbbox()
    if bbox is None:
        raise SystemExit(f"{name}: empty image")
    return image.crop(bbox)


def squared(image: Image.Image) -> Image.Image:
    """Centre the trimmed mark on a square transparent canvas."""
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def fit_width(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def save_pair(image: Image.Image, stem: str, webp: dict[str, int]) -> None:
    image.save(BRAND / f"{stem}.webp", "WEBP", **webp)
    image.save(BRAND / f"{stem}.png", "PNG", **PNG)


def on_paper(image: Image.Image, size: int, scale: float) -> Image.Image:
    """Opaque square icon: the mark scaled to `scale` of the side, on paper."""
    canvas = Image.new("RGBA", (size, size), PAPER)
    mark = image.resize((round(size * scale),) * 2, Image.Resampling.LANCZOS)
    offset = (size - mark.width) // 2
    canvas.alpha_composite(mark, (offset, offset))
    return canvas.convert("RGB")


def main() -> int:
    full = load_trimmed("logo-full.src.png")
    mark = squared(load_trimmed("logo-mark.src.png"))

    for width in FULL_WIDTHS:
        save_pair(fit_width(full, width), f"logo-full-{width}", WEBP_FULL)
    for size in MARK_SIZES:
        save_pair(mark.resize((size, size), Image.Resampling.LANCZOS), f"logo-mark-{size}", WEBP_MARK)

    mark.resize((32, 32), Image.Resampling.LANCZOS).save(BRAND / "favicon-32.png", "PNG", **PNG)
    mark.resize((192, 192), Image.Resampling.LANCZOS).save(BRAND / "icon-192.png", "PNG", **PNG)
    mark.resize((512, 512), Image.Resampling.LANCZOS).save(BRAND / "icon-512.png", "PNG", **PNG)
    # Apple ignores transparency (it becomes black), so the touch icon is opaque.
    on_paper(mark, 180, 0.86).save(BRAND / "apple-touch-icon.png", "PNG", **PNG)
    # Maskable: launchers may crop to a circle of 80% — the coin stays inside it.
    on_paper(mark, 512, 0.76).save(BRAND / "icon-512-maskable.png", "PNG", **PNG)

    ico_base = mark.resize((48, 48), Image.Resampling.LANCZOS)
    ico_base.save(ROOT / "favicon.ico", "ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    failed = False
    for name, limit in BUDGETS.items():
        size = (BRAND / name).stat().st_size
        status = "ok" if size <= limit else "OVER BUDGET"
        failed |= size > limit
        print(f"{name}: {size / 1024:.1f} KB (limit {limit // 1024} KB) {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
