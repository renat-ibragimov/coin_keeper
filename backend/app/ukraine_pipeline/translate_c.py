"""translate-c — LLM translation of the shared Ukrainian catalogue's remainder
(docs/05-integrations.md, part C).

Everything the earlier steps of the pipeline could name from an issuer's own
card already has an `official` title (`titles.py`, `circ_titles.py`,
`series.py`). What is left — legacy Excel imports with a Russian uCoin
heading and no National Bank card at all (`docs/BACKLOG.md`) — has no
official source to take a name from, so this step asks a model instead and
marks everything it writes `llm`. Official and manual names are never
selected, let alone overwritten.

Selection is idempotent by construction: a record counts as needing a slot
when that slot is empty *or* was written by an earlier run of this same step
(`*_source == 'llm'`), so a re-run only ever replaces its own prior guess.

`--dry-run` alone never calls the API — this step is the only one in the
pipeline that spends money per run, so the default is to show the selection
and the batch plan and stop there. Passing `--translate-out` on a dry run is
the deliberate exception: it does call the model, so the CSV it writes shows
real candidate translations for a person to check before `--apply`, but nothing
is written to the database either way without `--apply`.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CoinSeries, Denomination
from app.models.enums import TranslationSource

# A cheap, current model is enough for translating short catalogue titles.
MODEL = "claude-haiku-4-5"
BATCH_SIZE = 20
# One retry after an invalid batch response, then the batch goes to the report.
MAX_ATTEMPTS = 2

TOOL_NAME = "submit_translations"

SYSTEM_PROMPT = """You translate Ukrainian numismatic catalogue titles for a coin \
collection database maintained in the style of the National Bank of Ukraine's own \
catalogue.

Each item is a Ukrainian coin. You are given its raw stored title — sometimes \
Russian, sometimes a legacy import heading with the year, metal or weight glued \
onto the name — plus that year, denomination and material for context only.

For every item, return a clean canonical title:
- "titleUk": Ukrainian, in the National Bank's own wording style \
("Різдво Христове", not "Різдво (монета)" and not a literal word-for-word \
translation of the raw title);
- "titleEn": English, in the style of the English National Bank catalogue \
("The Nativity of Christ").

Never repeat the year, metal, weight or diameter in either title — they are \
already stored in their own columns. Never invent a title from nothing; \
translate and clean up what is given, do not guess a different coin."""


@dataclass(frozen=True)
class TranslationTask:
    """One catalog_items or coin_series row that needs an uk and/or en name."""

    id: int
    title: str
    year: int | None
    denomination: str | None
    material: str | None
    needs_uk: bool
    needs_en: bool


# A batch call: takes the tasks, returns a list of {"id", "titleUk", "titleEn"}
# dicts (any shape at all — validation happens in this module, not the caller),
# or raises. Production wiring is AnthropicTranslator below; tests supply a fake.
TranslateFn = Callable[[Sequence[TranslationTask]], Awaitable[Any]]


@dataclass
class TranslateOutcome:
    translated_uk: int = 0
    translated_en: int = 0
    series_translated_en: int = 0
    planned_items: int = 0
    planned_series: int = 0
    batches: int = 0
    retries: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    # id, the original string this replaced (Russian, for the Ukraine remainder),
    # its language, and the two generated names — the one place that string is
    # kept once title_original is overwritten below.
    rows: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "translatedUk": self.translated_uk,
            "translatedEn": self.translated_en,
            "seriesTranslatedEn": self.series_translated_en,
            "plannedItems": self.planned_items,
            "plannedSeries": self.planned_series,
            "batches": self.batches,
            "retries": self.retries,
            "errors": len(self.errors),
        }


def _needs(value: str | None, source: TranslationSource | None) -> bool:
    return not value or source == TranslationSource.LLM


def _chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


# ------------------------------------------------------------------- selection
async def select_item_tasks(
    session: AsyncSession, country_id: int
) -> tuple[dict[int, CatalogItem], list[TranslationTask]]:
    """Shared, non-archived Ukrainian records missing an official/manual uk or en name."""
    query = (
        select(CatalogItem, Denomination.value, Denomination.unit)
        .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
        .where(
            CatalogItem.country_id == country_id,
            CatalogItem.created_by.is_(None),
            or_(
                CatalogItem.title_uk.is_(None),
                CatalogItem.title_uk == "",
                CatalogItem.title_uk_source == TranslationSource.LLM,
                CatalogItem.title_en.is_(None),
                CatalogItem.title_en == "",
                CatalogItem.title_en_source == TranslationSource.LLM,
            ),
        )
        .order_by(CatalogItem.id)
    )
    items: dict[int, CatalogItem] = {}
    tasks: list[TranslationTask] = []
    for item, value, unit in (await session.execute(query)).all():
        needs_uk = _needs(item.title_uk, item.title_uk_source)
        needs_en = _needs(item.title_en, item.title_en_source)
        if not (needs_uk or needs_en):
            continue
        items[item.id] = item
        tasks.append(
            TranslationTask(
                id=item.id,
                title=item.title_original,
                year=item.issue_year,
                denomination=f"{value} {unit}" if value is not None and unit else None,
                material=item.material,
                needs_uk=needs_uk,
                needs_en=needs_en,
            )
        )
    return items, tasks


async def select_series_tasks(
    session: AsyncSession, country_id: int
) -> tuple[dict[int, CoinSeries], list[TranslationTask]]:
    """Ukrainian series missing an English name (docs/02-data-model.md's own gap)."""
    query = (
        select(CoinSeries)
        .where(
            CoinSeries.country_id == country_id,
            or_(
                CoinSeries.name_en.is_(None),
                CoinSeries.name_en == "",
                CoinSeries.name_en_source == TranslationSource.LLM,
            ),
        )
        .order_by(CoinSeries.id)
    )
    series = {s.id: s for s in (await session.execute(query)).scalars().all()}
    tasks = [
        TranslationTask(
            id=s.id,
            title=s.name_original,
            year=s.start_year,
            denomination=None,
            material=None,
            needs_uk=False,
            needs_en=True,
        )
        for s in series.values()
    ]
    return series, tasks


# --------------------------------------------------------------------- batches
def _validate_batch(
    tasks: Sequence[TranslationTask], response: Any
) -> dict[int, dict[str, str]] | None:
    """Strict: every id present, every needed field a non-empty string.

    Anything else — wrong shape, a missing id, an empty string where a
    translation was asked for — fails the whole batch rather than accepting
    it partially: a batch is retried once as a unit, see `_run_batch`.
    """
    if not isinstance(response, list):
        return None
    by_id: dict[int, dict[str, Any]] = {}
    for entry in response:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), int):
            return None
        by_id[entry["id"]] = entry

    result: dict[int, dict[str, str]] = {}
    for task in tasks:
        entry = by_id.get(task.id)
        if entry is None:
            return None
        title_uk, title_en = entry.get("titleUk"), entry.get("titleEn")
        if task.needs_uk and not (isinstance(title_uk, str) and title_uk.strip()):
            return None
        if task.needs_en and not (isinstance(title_en, str) and title_en.strip()):
            return None
        result[task.id] = {
            "titleUk": title_uk.strip() if isinstance(title_uk, str) else "",
            "titleEn": title_en.strip() if isinstance(title_en, str) else "",
        }
    return result


async def _run_batch(
    tasks: Sequence[TranslationTask], translate: TranslateFn, outcome: TranslateOutcome
) -> dict[int, dict[str, str]]:
    outcome.batches += 1
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await translate(tasks)
        except Exception:  # a network/parse failure is an invalid batch too
            response = None
        validated = _validate_batch(tasks, response) if response is not None else None
        if validated is not None:
            return validated
        if attempt < MAX_ATTEMPTS - 1:
            outcome.retries += 1
    outcome.errors.append({"ids": [task.id for task in tasks], "reason": "invalid batch response"})
    return {}


# ----------------------------------------------------------------------- apply
def _apply_item(
    item: CatalogItem,
    task: TranslationTask,
    translated: dict[str, str],
    outcome: TranslateOutcome,
    *,
    dry_run: bool,
) -> None:
    new_uk = translated["titleUk"] if task.needs_uk and translated["titleUk"] else None
    new_en = translated["titleEn"] if task.needs_en and translated["titleEn"] else None
    if new_uk is None and new_en is None:
        return
    old_original, old_lang = item.title_original, item.original_lang
    outcome.rows.append(
        {
            "id": item.id,
            "oldOriginal": old_original,
            "oldLang": old_lang,
            "newUk": new_uk,
            "newEn": new_en,
        }
    )
    if new_uk:
        outcome.translated_uk += 1
    if new_en:
        outcome.translated_en += 1
    if dry_run:
        return
    if new_uk:
        item.title_uk = new_uk
        item.title_uk_source = TranslationSource.LLM
        # For Ukraine the issuer's own language is Ukrainian (docs/02-data-model.md);
        # a Russian original left by the legacy Excel import is corrected here,
        # and the Russian string survives only in the review CSV from here on.
        if old_lang != "uk":
            item.title_original = new_uk
            item.original_lang = "uk"
    if new_en:
        item.title_en = new_en
        item.title_en_source = TranslationSource.LLM


def _apply_series(
    series: CoinSeries, translated: dict[str, str], outcome: TranslateOutcome, *, dry_run: bool
) -> None:
    if not translated["titleEn"]:
        return
    outcome.series_translated_en += 1
    if dry_run:
        return
    series.name_en = translated["titleEn"]
    series.name_en_source = TranslationSource.LLM


# ------------------------------------------------------------------------ main
async def run_translate_c(
    session: AsyncSession,
    *,
    country_id: int,
    translate: TranslateFn,
    dry_run: bool,
    call_api: bool,
    batch_size: int = BATCH_SIZE,
) -> TranslateOutcome:
    """`call_api` is False on a plain dry run: this step is the one place in the
    pipeline that spends money, so the default dry run only reports the
    selection and the batch plan. `--translate-out` turns it on for a dry run
    too, to produce a real CSV for review; `--apply` always turns it on.
    """
    outcome = TranslateOutcome()
    items, item_tasks = await select_item_tasks(session, country_id)
    series, series_tasks = await select_series_tasks(session, country_id)
    outcome.planned_items = len(item_tasks)
    outcome.planned_series = len(series_tasks)

    if call_api:
        for batch in _chunks(item_tasks, batch_size):
            validated = await _run_batch(batch, translate, outcome)
            for task in batch:
                translated = validated.get(task.id)
                if translated is not None:
                    _apply_item(items[task.id], task, translated, outcome, dry_run=dry_run)

        for batch in _chunks(series_tasks, batch_size):
            validated = await _run_batch(batch, translate, outcome)
            for task in batch:
                translated = validated.get(task.id)
                if translated is not None:
                    _apply_series(series[task.id], translated, outcome, dry_run=dry_run)

    if not dry_run:
        await session.flush()
    return outcome


# ---------------------------------------------------------------------- report
CSV_COLUMNS = ("id", "oldOriginal", "oldLang", "newUk", "newEn")


def write_review_csv(path: Path, outcome: TranslateOutcome) -> int:
    """One row per changed item — the Russian original stays only here.

    utf-8-sig: this is a report to be opened directly in Excel, not a review
    file this pipeline reads back (there is no --apply-review for this step;
    `--apply` recomputes and writes the same way `--translate-out` previewed).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.rows:
            writer.writerow({column: row.get(column, "") or "" for column in CSV_COLUMNS})
    return len(outcome.rows)


# ------------------------------------------------------------------- wiring
def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": "Return the translated titles for every item in the batch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "titleUk": {"type": "string"},
                            "titleEn": {"type": "string"},
                        },
                        "required": ["id", "titleUk", "titleEn"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _user_content(tasks: Sequence[TranslationTask]) -> str:
    payload = [
        {
            "id": task.id,
            "titleOriginal": task.title,
            "year": task.year,
            "denomination": task.denomination,
            "material": task.material,
        }
        for task in tasks
    ]
    return json.dumps(payload, ensure_ascii=False)


class AnthropicTranslator:
    """One batch call to the Anthropic Messages API (`TranslateFn`).

    The key never appears in a log line: it only ever reaches the SDK's own
    Authorization header.
    """

    def __init__(self, api_key: str, model: str = MODEL) -> None:
        import anthropic  # local: only the translate-c step needs the SDK at all

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def __call__(self, tasks: Sequence[TranslationTask]) -> list[dict[str, Any]] | None:
        response = await self._client.messages.create(  # type: ignore[call-overload]
            model=self._model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[_tool_schema()],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[{"role": "user", "content": _user_content(tasks)}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == TOOL_NAME:
                translations = block.input.get("translations")
                return translations if isinstance(translations, list) else None
        return None
