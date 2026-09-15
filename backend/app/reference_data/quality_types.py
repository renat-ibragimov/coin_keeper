"""Strike quality as a reference row, mirroring `materials.py`.

Seeded from what the confirmed (Ukrainian) catalogue actually contains: six
values, populated in `catalog_items.quality` by a one-off pass whose script
is no longer in the repository, and never surfaced in the API or the
interface until now (docs/04-business-rules.md, rule 14).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QualityTypeSeed:
    code: str
    name_uk: str
    name_en: str


QUALITY_TYPES: tuple[QualityTypeSeed, ...] = (
    QualityTypeSeed("uncirculated", "Анциркулейтед", "Uncirculated"),
    QualityTypeSeed("special_uncirculated", "Спеціальний анциркулейтед", "Special uncirculated"),
    QualityTypeSeed("proof", "Пруф", "Proof"),
    QualityTypeSeed("proof_like", "Пруф-лайк", "Proof-like"),
    QualityTypeSeed("improved", "Покращена якість", "Improved quality"),
    QualityTypeSeed("not_specified", "Не вказано", "Not specified"),
)

QUALITY_TYPE_CODES = frozenset(quality_type.code for quality_type in QUALITY_TYPES)

LEGACY_ALIASES: dict[str, str] = {code: code for code in QUALITY_TYPE_CODES}


def resolve_quality_code(text: str | None) -> str | None:
    """The dictionary code for a raw `quality` value, or None if unrecognised."""
    if not text:
        return None
    return LEGACY_ALIASES.get(text.strip().casefold())
