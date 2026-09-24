"""One short phrase, translated by Claude Haiku (docs/05-integrations.md).

Single calls for single user-typed phrases, meant to run detached from the
request in a FastAPI BackgroundTask right after the row is saved: never block
the response, and a failure just leaves the untranslated placeholder in place
rather than surfacing an error to the user.

Two phrases, two prompts, one shape of answer (`TranslationResult`):

* a storage location ("вдома", "at my parents'") — `translate_short_phrase`;
* the name of a coin a collector entered by hand — `translate_coin_title`.

The second is not the first with a longer input. Coin names are full of
proper nouns, place names and the titles of commemorative programmes, and a
translator told only "translate this phrase" mangles exactly those. The rule
both share, and the reason the shape is the same: the language the phrase is
already in comes back untouched, character for character.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger("app.services.translation")

# A cheap, current model is enough for translating a couple of words.
MODEL = "claude-haiku-4-5"

TOOL_NAME = "submit_translation"

SYSTEM_PROMPT = """You translate a short phrase a coin collector typed to describe \
where they keep a coin (for example "вдома", "у банку", "at my parents'"). Detect \
which language it is written in, then provide both a Ukrainian and an English \
version that read naturally to a collector -- a plain, direct translation, not a \
rewording or an explanation. If the phrase is already Ukrainian or already \
English, that language's own slot must be returned completely unchanged, \
character for character."""


COIN_TITLE_SYSTEM_PROMPT = """You translate the name of a coin for a numismatic \
catalogue. A collector typed it while recording a coin they own, and you are given \
the issuing country and the year of issue as context.

Detect which language the name is written in, then give a Ukrainian and an English \
version.

Rules:
- Translate as a numismatic catalogue would: the name of the coin, in natural \
wording, not a word-for-word gloss and not an explanation.
- Proper nouns stay proper nouns. Place names take their established form in the \
target language (Львів -> Lviv, Одеса -> Odesa), never a transliteration invented \
on the spot; the names of commemorative programmes, organisations and monuments \
keep their official wording in that language (ЮНЕСКО -> UNESCO).
- Never add the year, denomination, metal, weight or diameter to a name. They are \
stored in columns of their own. If the given name contains them, leave them out of \
both versions.
- Never invent a different coin. If the name is too short or too vague to place \
confidently, transliterate the proper part and translate the rest literally rather \
than guessing at what the coin commemorates.
- The language the name is already written in must come back completely unchanged, \
character for character."""


@dataclass(frozen=True)
class TranslationResult:
    language: Literal["uk", "en", "other"]
    name_uk: str
    name_en: str


def _tool_schema() -> dict[str, object]:
    return {
        "name": TOOL_NAME,
        "description": "Report the detected language and both translations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "enum": ["uk", "en", "other"]},
                "nameUk": {"type": "string"},
                "nameEn": {"type": "string"},
            },
            "required": ["language", "nameUk", "nameEn"],
        },
    }


def _parse(data: object) -> TranslationResult | None:
    if not isinstance(data, dict):
        return None
    language = data.get("language")
    name_uk = data.get("nameUk")
    name_en = data.get("nameEn")
    if language not in ("uk", "en", "other"):
        return None
    if not isinstance(name_uk, str) or not isinstance(name_en, str):
        return None
    if not name_uk.strip() or not name_en.strip():
        return None
    return TranslationResult(language=language, name_uk=name_uk, name_en=name_en)


async def _translate(
    *, system: str, content: str, api_key: str, max_tokens: int
) -> TranslationResult | None:
    """None on any failure (network, quota, malformed reply) -- the caller
    keeps whatever placeholder it already has rather than raising."""
    import anthropic  # local: only this path needs the SDK loaded

    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(  # type: ignore[call-overload]
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            tools=[_tool_schema()],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError:
        logger.exception("Haiku translation call failed")
        return None
    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            return _parse(block.input)
    logger.warning("Haiku reply had no %s tool_use block", TOOL_NAME)
    return None


async def translate_short_phrase(phrase: str, api_key: str) -> TranslationResult | None:
    return await _translate(system=SYSTEM_PROMPT, content=phrase, api_key=api_key, max_tokens=256)


async def translate_coin_title(
    title: str, api_key: str, *, country: str | None = None, year: int | None = None
) -> TranslationResult | None:
    """The name of a hand-entered coin. Country and year are context only —
    the prompt forbids putting either of them into the name itself."""
    lines = [f"Name as typed: {title}"]
    if country:
        lines.append(f"Issuer: {country}")
    if year:
        lines.append(f"Year of issue: {year}")
    return await _translate(
        system=COIN_TITLE_SYSTEM_PROMPT,
        content="\n".join(lines),
        api_key=api_key,
        max_tokens=512,
    )
