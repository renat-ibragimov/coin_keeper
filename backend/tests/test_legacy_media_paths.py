"""Extracting a file name from a legacy media path.

The desktop application ran on Windows and stored absolute paths. The first
real dry run reported 2270 local rows and not a single file found, because
pathlib.Path on POSIX does not treat a backslash as a separator.
"""

from __future__ import annotations

import pytest

from app.legacy_migration.media import file_name_from, is_external

WINDOWS_REAL = (
    r"C:\Users\<user>\AppData\Roaming\CoinKeeper Data"
    r"\media\5_obverse_02374f5ab2494c21b315d245c92d78cd.jpg"
)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        # The shape the production database actually holds.
        (WINDOWS_REAL, "5_obverse_02374f5ab2494c21b315d245c92d78cd.jpg"),
        # Spaces in the directory must not confuse it.
        (r"D:\Coin Keeper\media\10_additional_z.jpeg", "10_additional_z.jpeg"),
        # Forward slashes, with a space again.
        ("/home/user/CoinKeeper Data/media/7_reverse_abc.jpg", "7_reverse_abc.jpg"),
        # A bare name is left exactly as it is.
        ("1023_obverse_eb5c6f1c.jpg", "1023_obverse_eb5c6f1c.jpg"),
        # Relative Windows path.
        (r"..\media\9_edge_y.jpg", "9_edge_y.jpg"),
        # Drive-relative: the drive letter is not part of the name.
        (r"C:5_obverse_x.jpg", "5_obverse_x.jpg"),
        # Surrounding whitespace from a sloppy write.
        ("  1023_obverse_a.jpg  ", "1023_obverse_a.jpg"),
    ],
)
def test_file_name_is_extracted_from_either_convention(stored: str, expected: str) -> None:
    assert file_name_from(stored) == expected


def test_extension_case_is_preserved() -> None:
    """The name is looked up on disk as stored, so case must survive."""
    assert file_name_from(r"C:\media\9_edge_y.PNG") == "9_edge_y.PNG"
    assert file_name_from(r"C:\media\9_edge_y.JPEG") == "9_edge_y.JPEG"


def test_external_links_are_still_recognised_by_scheme_alone() -> None:
    """The external/local split is unchanged: only the scheme decides."""
    assert is_external("https://i.ucoin.net/coin/50/796/x.jpg") is True
    assert is_external("http://example.com/photo.jpg") is True
    assert is_external(WINDOWS_REAL) is False
    assert is_external("1023_obverse_a.jpg") is False
