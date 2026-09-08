"""roll_photos: matching a "Ми сильні. Ми разом." title to its ua-coins slug.

oblast_slug is checked against all twelve real oblast names the ua-coins
"розмінні та обігові" listing carries (docs/05-integrations.md, section 9's
roll note) — not invented pairs, the same twelve
tests/fixtures/ukraine_recon/ua_coins_regular_ua_listing.html holds.
"""

from __future__ import annotations

from pathlib import Path

from app.ukraine_pipeline import roll_photos
from app.ukraine_recon import ua_coins

FIXTURES = Path(__file__).parent / "fixtures" / "ukraine_recon"

# (Ukrainian oblast name as our titles spell it, the slug fragment ua-coins
# actually uses) — read straight off the twelve real "Ми сильні" rows.
REAL_OBLASTS = [
    ("Запорізька область", "zaporizka-oblast"),
    ("Харківська область", "kharkivska-oblast"),
    ("Херсонська область", "khersonska-oblast"),
    ("Луганська область", "luhanska-oblast"),
    ("Донецька область", "donetska-oblast"),
    ("Автономна Республіка Крим", "avtonomna-respublika-krym"),
    ("Миколаївська область", "mykolayivska-oblast"),
    ("Одеська область", "odeska-oblast"),
    ("Чернігівська область", "chernihivska-oblast"),
    ("Сумська область", "sumska-oblast"),
    ("Дніпропетровська область", "dnipropetrovska-oblast"),
    ("Кіровоградська область", "kirovohradska-oblast"),
]


def test_oblast_slug_matches_every_real_ua_coins_slug() -> None:
    for name_uk, slug in REAL_OBLASTS:
        assert roll_photos.oblast_slug(name_uk) == slug


def test_oblast_name_strips_the_series_prefix() -> None:
    assert roll_photos.oblast_name("Ми сильні. Ми разом. Одеська область") == "Одеська область"
    assert roll_photos.oblast_name("Області України. Одеська область") is None


def test_match_candidates_against_the_real_listing_fixture() -> None:
    html = (FIXTURES / "ua_coins_regular_ua_listing.html").read_text(encoding="utf-8")
    listing = ua_coins.parse_regular_ua_listing(html)
    items = [
        (1, "Ми сильні. Ми разом. Запорізька область"),
        (2, "Ми сильні. Ми разом. Дніпропетровська область"),
        (3, "Ми сильні. Ми разом. Кіровоградська область"),
        (4, "1 гривня 2018 року"),  # no series prefix: never a candidate
    ]
    candidates = roll_photos.match_candidates(items, listing)
    found = {candidate.item_id: candidate.url for candidate in candidates}
    assert found[1] == (
        "https://www.ua-coins.info/ua/show-regular-ua/"
        "280-obihova-pam-yatna-moneta-10-hryven-my-sylni-my-razom-zaporizka-oblast"
    )
    assert found[2] == (
        "https://www.ua-coins.info/ua/show-regular-ua/"
        "291-obihova-pam-yatna-moneta-10-hryven-my-sylni-my-razom-dnipropetrovska-oblast"
    )
    assert found[3] == (
        "https://www.ua-coins.info/ua/show-regular-ua/"
        "292-obihova-pam-yatna-moneta-10-hryven-my-sylni-my-razom-kirovohradska-oblast"
    )
    assert 4 not in found


def test_match_candidates_leaves_an_unlisted_oblast_blank() -> None:
    found = roll_photos.match_candidates(
        [(1, "Ми сильні. Ми разом. Вигадана область")], {"280-...-zaporizka-oblast": "x"}
    )
    assert found == []
