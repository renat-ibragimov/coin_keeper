"""inventory-b — a survey of what part B's bridge left unlinked (~100 records).

Not heroics: a CSV, for a person to read. Every active Ukrainian
commemorative/collector record with no NBU link at all
(`OurItem.is_nbu_linked`) is one row, with a metal guess read off its own
title text and up to three fuzzy NBU candidates (the same `Lexicon.score`
and `REVIEW_THRESHOLD` app/ukraine_pipeline/bridge.py already uses, against
`Sources.nbu` — the same cached scrape bridge/series/gaps already need, so
running this step alongside them costs nothing extra in requests).

**Only `link` is ever applied.** `suggestedAction` is `link` when a
candidate cleared the threshold, `archive` when the title itself says this
is a yearly set ("річний набір" and its kin) — `collection_group` has no
enum value for a set (`docs/02-data-model.md`), and the handoff's own
instruction is a CSV suggestion with a reason, not a schema change for one
label — and `manual` otherwise ("через admin", outside this task's scope).
`archive`/`manual` rows are read by a person, never written by this step.

The review CSV deliberately uses the exact column shape
app/ukraine_pipeline/jubilee_bridge.py already reads
(`decision`/`itemId`/`nbuId`): `jubilee_bridge.read_review_csv` and
`jubilee_bridge.write_links` apply a `link` decision here unchanged, so
there is one apply mechanism for both tools, not two.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.ukraine_pipeline.bridge import REVIEW_THRESHOLD
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.lexicon import Lexicon
from app.ukraine_pipeline.sources import Sources
from app.ukraine_recon.models import SOURCE_NBU

MAX_CANDIDATES = 3
# Ukrainian and Russian both appear in our title_original (rule 2, the two
# Excel imports this remainder came from) — checked without a language guess.
SET_MARKERS = (
    "річний набір",
    "річного набору",
    "набір монет",
    "у наборі",
    "набор монет",
    "годовой набор",
    "годового набора",
)
GOLD_MARKERS = ("золот",)
SILVER_MARKERS = ("срібн", "серебр")

CSV_COLUMNS = (
    "decision",
    "itemId",
    "nbuId",
    "title",
    "year",
    "metalGuess",
    "nbuCandidates",
    "suggestedAction",
)


def metal_guess(title: str) -> str:
    lowered = title.casefold()
    if any(marker in lowered for marker in GOLD_MARKERS):
        return "золото"
    if any(marker in lowered for marker in SILVER_MARKERS):
        return "срібло"
    return "не визначено"


def is_set(title: str) -> bool:
    lowered = title.casefold()
    return any(marker in lowered for marker in SET_MARKERS)


@dataclass
class InventoryRow:
    item: OurItem
    metal: str
    candidates: list[tuple[str, str, float]]  # (nbu card id, title, score)
    suggested_action: str


@dataclass
class InventoryOutcome:
    rows: list[InventoryRow] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        for row in self.rows:
            by_action[row.suggested_action] = by_action.get(row.suggested_action, 0) + 1
        return {"rows": len(self.rows), "byAction": by_action}


def _candidates(item: OurItem, sources: Sources, lexicon: Lexicon) -> list[tuple[str, str, float]]:
    scored: list[tuple[str, str, float]] = []
    for record in sources.nbu:
        if record.year is not None and abs(record.year - item.issue_year) > 1:
            continue
        title = record.title_uk or ""
        if not title or not record.source_id:
            continue
        score = lexicon.score(item.title_original, title)
        if score >= REVIEW_THRESHOLD:
            scored.append((record.source_id, title, score))
    scored.sort(key=lambda candidate: -candidate[2])
    return scored[:MAX_CANDIDATES]


def build_inventory(items: list[OurItem], sources: Sources, lexicon: Lexicon) -> InventoryOutcome:
    outcome = InventoryOutcome()
    for item in items:
        if item.is_archived or item.is_nbu_linked or not item.is_commemorative:
            continue
        if SOURCE_NBU in item.links:
            continue
        candidates = _candidates(item, sources, lexicon)
        if candidates:
            action = "link"
        elif is_set(item.title_original):
            action = "archive"
        else:
            action = "manual"
        outcome.rows.append(
            InventoryRow(
                item=item,
                metal=metal_guess(item.title_original),
                candidates=candidates,
                suggested_action=action,
            )
        )
    return outcome


def write_csv(path: Path, outcome: InventoryOutcome) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.rows:
            top = row.candidates[0] if row.candidates else None
            writer.writerow(
                {
                    "decision": "",
                    "itemId": row.item.id,
                    "nbuId": top[0] if top else "",
                    "title": row.item.title_original,
                    "year": row.item.issue_year,
                    "metalGuess": row.metal,
                    "nbuCandidates": " | ".join(
                        f"{cid}:{title}:{round(score, 1)}" for cid, title, score in row.candidates
                    ),
                    "suggestedAction": row.suggested_action,
                }
            )
    return len(outcome.rows)
