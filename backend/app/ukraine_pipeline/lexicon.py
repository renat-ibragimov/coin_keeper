"""Comparing a Russian title with a Ukrainian one.

Our Ukrainian coins came from the Russian locale of uCoin, and all three
sources write Ukrainian. A plain fuzzy ratio is not enough: "Хмельницкий" and
"Хмельницький" differ by letters that carry no meaning here, while "лет" and
"років" are the same word and share almost nothing.

Two steps, in this order:

1. a word dictionary (lexicon.json), Russian to Ukrainian, applied to whole
   words — that is the only way "рождения" reaches "народження";
2. letter folding, which collapses the orthographic pairs (і/и/ї/й, є/е/э/ё,
   ґ/г) and drops the soft and hard signs.

Folding after the dictionary, not before: the dictionary is written in real
spelling so a person can read and extend it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from rapidfuzz import fuzz

from app.reference_data.materials import strip_material
from app.ukraine_recon.normalize import bare_title, normalize_title

LEXICON_PATH = Path(__file__).with_name("lexicon.json")

# One name's words all appearing in the other is strong evidence, but not the
# same as the names being equal.
CONTAINMENT_SCORE = 95.0
MEANINGFUL_WORD = 3

# Letters that differ between the two spellings without differing in meaning.
_FOLD = str.maketrans(
    {
        "і": "и",
        "ї": "и",
        "й": "и",
        "ы": "и",
        "є": "е",
        "э": "е",
        "ё": "е",
        "ґ": "г",
        "ь": "",
        "ъ": "",
        "'": "",
        "’": "",
    }
)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
# Our titles often carry the series in front: "Флора и фауна - Соня садовая",
# where the sources name the coin alone. The tail is compared as well.
_SERIES_PREFIX_RE = re.compile(r"^.{3,}?\s[-–—]\s(?=.{3,}$)")
# The uCoin importer wrote the whole heading into the title of 460 of our
# 1060 Ukrainian commemoratives: "2.000.000 карбованцев, 1995 50 лет ООН
# AgСеребро 0.925, 33.62g". The denomination and year come off here, the
# material through strip_material.
_HEADING_RE = re.compile(
    r"^\s*[\d\s.,]+\s*"
    r"(?:гривен|гривень|гривны|гривня|гривні|копе\w+|копі\w+|карбованц\w+|крб)\.?"
    r"\s*,\s*\d{4}(?:\s*[-–—]\s*\d{4})?\s+",
    re.IGNORECASE,
)


def strip_import_noise(title: str) -> str:
    """The coin's name out of what the importer stored as its name."""
    return _HEADING_RE.sub("", strip_material(title)).strip()


@dataclass(frozen=True, slots=True)
class Lexicon:
    words: dict[str, str]

    def translate(self, text: str) -> str:
        return _WORD_RE.sub(lambda m: self.words.get(m.group(0), m.group(0)), text)

    def fold(self, title: str) -> str:
        """One comparable form for a title written in either language."""
        folded = self.translate(normalize_title(bare_title(title))).translate(_FOLD)
        # normalize_title decomposes (NFKD), so "ї" arrives as "і" plus a
        # combining diaeresis; folding "і" to "и" would otherwise leave the
        # mark behind and produce a letter nobody writes.
        return "".join(ch for ch in folded if not unicodedata.combining(ch))

    def score(self, ours: str, theirs: str) -> float:
        """0..100, the best of the forms our title can reasonably take."""
        right = self.fold(theirs)
        if not right:
            return 0.0
        return max((self._score_one(form, right) for form in self._forms(ours)), default=0.0)

    def _forms(self, title: str) -> list[str]:
        """The title as it is, and — if it starts with a series — without it.

        The prefix has to go before normalisation: the dash that marks it is
        punctuation, and normalisation turns punctuation into spaces.
        """
        cleaned = strip_import_noise(title) or title
        forms = [self.fold(cleaned)]
        without_series = _SERIES_PREFIX_RE.sub("", cleaned)
        if without_series != cleaned:
            forms.append(self.fold(without_series))
        return forms

    @staticmethod
    def _score_one(left: str, right: str) -> float:
        if not left:
            return 0.0
        if left == right:
            return 100.0
        # The prefix rule of docs/05-integrations.md: Wikipedia and the NBU
        # often carry the same name with a qualifier appended.
        if left.startswith(right + " ") or right.startswith(left + " "):
            return 97.0
        if _one_contains_the_other(left, right):
            # The NBU names a coin as tersely as it can — "Кий", "Ольга" —
            # where our title says "Князь Кий". Every word of the shorter name
            # is in the longer one, which a character ratio cannot see on
            # strings this short.
            return CONTAINMENT_SCORE
        return float(fuzz.token_sort_ratio(left, right))


def _one_contains_the_other(left: str, right: str) -> bool:
    """Every word of the shorter name is a word of the longer one.

    Guarded by a real word: two titles sharing only "рік" or "у" say nothing.
    """
    left_words, right_words = set(left.split()), set(right.split())
    if not left_words or not right_words:
        return False
    smaller = left_words if len(left_words) <= len(right_words) else right_words
    larger = right_words if smaller is left_words else left_words
    if not smaller <= larger:
        return False
    return any(len(word) >= MEANINGFUL_WORD for word in smaller)


@cache
def load_lexicon(path: Path = LEXICON_PATH) -> Lexicon:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Lexicon(words=dict(payload["words"]))
