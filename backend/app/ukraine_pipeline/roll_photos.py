"""roll_photos — the clean obverse/reverse ua-coins.info has for a roll coin.

app/ukraine_pipeline/sources.py:roll_coin reads "Ми сильні. Ми разом.
<область>" off the National Bank's roll card, and the photo that comes with
it (app/ukraine_pipeline/photos.py) is the roll's own packaging shot, not
the coin (docs/05-integrations.md, the "Ми сильні" note in
app/ukraine_recon/series_map.json). ua-coins.info separately lists these
same twelve coins under its "розмінні та обігові" section
(`app/ukraine_recon/ua_coins.py:regular_ua_listing_url`), with an ordinary
clean obverse/reverse pair each — not a roll photo.

This module is the matching step between the two: our title names an
oblast in Ukrainian ("Одеська область"), the ua-coins slug names the same
one transliterated ("...-odeska-oblast"). `oblast_slug` is the official
Ukrainian romanisation (Cabinet of Ministers resolution 55/2010), verified
against all twelve real slugs the listing carries
(tests/fixtures/ukraine_recon/ua_coins_regular_ua_listing.html) — not a
general-purpose transliterator, just enough of the alphabet for an oblast
name.

Deliberately narrow: matching an arbitrary title against an arbitrary
ua-coins section is the crawler docs/BACKLOG.md defers to later. This only
ever looks at "Ми сильні. Ми разом.%" titles and the one listing they live
under.
"""

from __future__ import annotations

from dataclasses import dataclass

TITLE_PREFIX = "Ми сильні. Ми разом."

# Official Ukrainian Latin transliteration (Cabinet of Ministers resolution
# No. 55, 2010), the subset an oblast name actually uses. "ь" and the two
# apostrophe forms drop silently; a space becomes the slug's own "-".
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "yi", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ю": "iu", "я": "ia",
    "ь": "", "'": "", "’": "", "ʼ": "",
}  # fmt: skip


def oblast_slug(name_uk: str) -> str:
    """ "Одеська область" -> "odeska-oblast": the fragment ua-coins' own slug carries."""
    pieces = [" " if ch == " " else _TRANSLIT.get(ch, ch) for ch in name_uk.strip().casefold()]
    return "-".join("".join(pieces).split())


def oblast_name(title_original: str) -> str | None:
    """The part after "Ми сильні. Ми разом." — None for a title without it."""
    if not title_original.startswith(TITLE_PREFIX):
        return None
    name = title_original[len(TITLE_PREFIX) :].strip()
    return name or None


@dataclass(frozen=True, slots=True)
class Candidate:
    item_id: int
    title: str
    url: str


def match_candidates(items: list[tuple[int, str]], listing: dict[str, str]) -> list[Candidate]:
    """Our (item id, title) pairs matched to a "show-regular-ua" URL from the listing.

    `listing` is app/ukraine_recon/ua_coins.py:parse_regular_ua_listing's own
    {slug: url} map. A title whose oblast fragment is not a substring of any
    slug is left out — nothing here guesses at a near match, the CSV column
    for it just stays blank for a person to fill in by hand.
    """
    found: list[Candidate] = []
    for item_id, title in items:
        name = oblast_name(title)
        if name is None:
            continue
        fragment = oblast_slug(name)
        url = next((url for slug, url in listing.items() if fragment in slug), None)
        if url is not None:
            found.append(Candidate(item_id=item_id, title=title, url=url))
    return found
