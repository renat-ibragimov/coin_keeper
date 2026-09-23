"""Run with Python + Pillow to regenerate the landing's delivery assets.

Keep PNG originals for future edits. Preserve dimensions and alpha so that
the existing CSS crop, masks and theme blending remain unchanged.
"""

from pathlib import Path

from PIL import Image


assets = Path(__file__).resolve().parents[1] / "src/features/landing/assets"
for name in ("books-new", "album-new", "expense-ledger"):
    source = assets / f"{name}.png"
    target = assets / f"{name}.webp"
    with Image.open(source) as image:
        image.save(target, "WEBP", quality=85, method=6, exact=True)
    print(f"{source.name}: {source.stat().st_size:,} -> {target.stat().st_size:,} bytes")
