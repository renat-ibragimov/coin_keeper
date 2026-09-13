"""One short phrase, translated by Claude Haiku (docs/05-integrations.md).

Not the batch/CSV pipeline in app/ukraine_pipeline/translate_c.py — that one
is an offline, human-reviewed run over the shared catalogue. This is a single
call for a single user-typed phrase (a custom storage location so far), meant
to run detached from the request in a FastAPI BackgroundTask right after the
row is saved: never blocks the response, and a failure just leaves the
untranslated placeholder in place rather than surfacing an error to the user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger("app.services.translation")

# A cheap, current model is enough for translating a couple of words —
# the same convention app/ukraine_pipeline/translate_c.py uses.
MODEL = "claude-haiku-4-5"

TOOL_NAME = "submit_translation"

SYSTEM_PROMPT = """You translate a short phrase a coin collector typed to describe \
where they keep a coin (for example "вдома", "у банку", "at my parents'"). Detect \
which language it is written in, then provide both a Ukrainian and an English \
version that read naturally to a collector -- a plain, direct translation, not a \
rewording or an explanation. If the phrase is already Ukrainian or already \
English, that language's own slot must be returned completely unchanged, \
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


async def translate_short_phrase(phrase: str, api_key: str) -> TranslationResult | None:
    """None on any failure (network, quota, malformed reply) -- the caller
    keeps whatever placeholder it already has rather than raising."""
    import anthropic  # local: only this path needs the SDK loaded

    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(  # type: ignore[call-overload]
            model=MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            tools=[_tool_schema()],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": phrase}],
        )
    except anthropic.APIError:
        logger.exception("Haiku translation call failed")
        return None
    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            return _parse(block.input)
    logger.warning("Haiku reply had no %s tool_use block", TOOL_NAME)
    return None
