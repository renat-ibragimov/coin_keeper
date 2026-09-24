"""Background translation of a hand-entered coin title.

The model is never called here. `apply_title_translation` is pure and
DB-free — the same split storage locations use (tests/test_storage_locations.py)
— so the one part with a real judgment call, which slot to touch, is testable
on its own.
"""

from __future__ import annotations

import pytest

from app.models import CatalogItem
from app.models.enums import CollectionGroup, TranslationSource
from app.services.catalog import apply_title_translation
from app.services.translation import TranslationResult


def make_item(title: str) -> CatalogItem:
    """A personal item as `create_personal_item` leaves it: both slots hold
    the typed text, both marked manual."""
    return CatalogItem(
        country_id=1,
        collection_group=CollectionGroup.COMMEMORATIVE,
        title_original=title,
        title_uk=title,
        title_uk_source=TranslationSource.MANUAL,
        title_en=title,
        title_en_source=TranslationSource.MANUAL,
        issue_year=2021,
        created_by=1,
    )


def test_a_ukrainian_title_keeps_its_own_slot_verbatim() -> None:
    item = make_item("Львівський оперний театр")
    apply_title_translation(
        item,
        # The model is asked for both slots and answers both; the Ukrainian
        # one is thrown away in favour of what the collector typed.
        TranslationResult(
            language="uk", name_uk="Львівський театр опери", name_en="Lviv Opera House"
        ),
    )
    assert item.title_uk == "Львівський оперний театр"
    assert item.title_uk_source == TranslationSource.MANUAL
    assert item.title_en == "Lviv Opera House"
    assert item.title_en_source == TranslationSource.LLM


def test_an_english_title_keeps_its_own_slot_verbatim() -> None:
    item = make_item("Silver Eagle")
    apply_title_translation(
        item, TranslationResult(language="en", name_uk="Срібний орел", name_en="Silver eagle")
    )
    assert item.title_en == "Silver Eagle"
    assert item.title_en_source == TranslationSource.MANUAL
    assert item.title_uk == "Срібний орел"
    assert item.title_uk_source == TranslationSource.LLM


def test_a_third_language_fills_both_slots() -> None:
    """Russian is the usual case here: the Soviet part of the catalogue is
    stored in Russian because that is the issuer's own wording, and a title
    typed in it is translated rather than copied (CLAUDE.md)."""
    item = make_item("Ленинградский монетный двор")
    apply_title_translation(
        item,
        TranslationResult(
            language="other", name_uk="Ленінградський монетний двір", name_en="Leningrad Mint"
        ),
    )
    assert item.title_original == "Ленинградский монетный двор"
    assert item.title_uk == "Ленінградський монетний двір"
    assert item.title_uk_source == TranslationSource.LLM
    assert item.title_en == "Leningrad Mint"
    assert item.title_en_source == TranslationSource.LLM


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "Lviv Opera House",
        {"language": "uk", "nameUk": "", "nameEn": "Lviv Opera House"},
        {"language": "martian", "nameUk": "a", "nameEn": "b"},
        {"nameUk": "a", "nameEn": "b"},
    ],
)
def test_an_unusable_reply_is_rejected_before_it_reaches_a_row(payload: object) -> None:
    """`_parse` is what stands between a malformed answer and the database;
    a rejected one means the coin keeps the collector's own wording."""
    from app.services.translation import _parse

    assert _parse(payload) is None


def test_the_coin_prompt_is_not_the_storage_location_one() -> None:
    """Two phrases, two prompts (docs/integrations.md, раздел 11): coin
    names are full of proper nouns, and the rules that protect them have no
    business in a prompt about where a coin is kept."""
    from app.services.translation import COIN_TITLE_SYSTEM_PROMPT, SYSTEM_PROMPT

    assert COIN_TITLE_SYSTEM_PROMPT != SYSTEM_PROMPT
    assert "Lviv" in COIN_TITLE_SYSTEM_PROMPT
    assert "character for character" in COIN_TITLE_SYSTEM_PROMPT
