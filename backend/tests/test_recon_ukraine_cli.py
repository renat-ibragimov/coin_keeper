"""Command line of scripts/recon_ukraine.py: arguments and the usage errors."""

from __future__ import annotations

from pathlib import Path

from scripts import recon_ukraine


def test_defaults_are_the_documented_ones() -> None:
    args = recon_ukraine._parse_args([])
    assert args.ua_coins == "auto"
    assert args.image_sample == 50
    assert args.pause == 0.45
    assert args.skip_catalog is False
    assert args.report.name == "recon-report.json"


def test_missing_catalog_export_is_a_usage_error(tmp_path: Path, capsys: object) -> None:
    code = recon_ukraine.main(["--catalog-from", str(tmp_path / "missing.json")])
    assert code == recon_ukraine.EXIT_USAGE


def test_image_dimensions_from_headers() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (1600).to_bytes(4, "big")
        + (1600).to_bytes(4, "big")
    )
    assert recon_ukraine._image_dimensions(png) == (1600, 1600)
    webp = (
        b"RIFF\x00\x00\x00\x00WEBPVP8 "
        + b"\x00" * 10
        + (300).to_bytes(2, "little")
        + (200).to_bytes(2, "little")
    )
    assert recon_ukraine._image_dimensions(webp) == (300, 200)
    assert recon_ukraine._image_dimensions(b"nope") is None
