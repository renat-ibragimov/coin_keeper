"""merge-b — the Excel remainder that already has a twin in our own catalogue.

136 active shared Ukrainian records (country_id, commemorative/collector/other —
docs/02-data-model.md's `collection_group` has four values, not the two or three
some earlier code and docs assumed) carry no National Bank link at all
(`OurItem.is_nbu_linked`): no `price_source_links` row, no `nbu:<id>` source key.
Diagnosed by hand against the owner's database, 2026-09-05: 118 of the 136 are not
missing coins, they are **duplicates** — the legacy Excel migration imported them
under a Russian uCoin heading ("10 гривен, 1996 400 лет со дня рождения Петра
Могили AgСеребро 0.925, 16.94g, ø 33mm") next to a record `gaps.py` (part B) later
created for the very same coin from the National Bank's own card ("Петро Могила",
`nbu:33`). `app/ukraine_pipeline/merge.py` already does exactly this move for the
duplicates `gaps.py` itself produces; this module finds the pairs `merge.py`'s own
key (same year, same slot from `gaps`'s own source key) cannot see, because these
orphans were never touched by `gaps` at all — they came in years before it, by
Excel, not by the pipeline.

**Why part B's own bridge (`bridge.py`) and `circ_inventory.py` (`inventory-b`,
despite the name, a survey of the *commemorative* remainder) never surfaced this
pairing themselves.** Both score a title against the *entire* National Bank
catalogue and only trust a candidate at or above `bridge.REVIEW_THRESHOLD` (55) —
a threshold sized for an open search across ~1000 cards, where a coincidental
resemblance is a real risk. `Lexicon.score` already strips the material tail and
the Excel heading before comparing (`lexicon.strip_import_noise`), and still the
Mohyla pair above scores 46, Desiatynna's 50 — both below that open-search bar
(`test_merge_b.py` asserts this against `bridge.REVIEW_THRESHOLD` directly, so a
future change to either number is a visible break, not a silent regression). What
changes here is the search space, not the arithmetic: `find_orphans` only scores
an orphan against records that already share its (`issue_year`, `denomination_id`)
— a slot with at most a handful of the National Bank's ~1000 cards in it, most
years just one or two — so a coincidental match is not the risk a lower floor
would run, and `clean_orphan_title` (`strip_import_noise` under a name of its own,
tested here directly against the Mohyla/Desiatynna titles from the diagnosis) is
what keeps a candidate's own weight-and-fineness noise from drowning that
comparison. A slot can still hold several legitimate coins of its own — "5 hryvnia
2018" is one — which is why a top score only becomes `suggestedTwinId` when it
clearly leads the runner-up; a close call is `manual`, a person's call.

**Never auto-merged.** Even a clean top score only ever fills `suggestedTwinId`
in the review CSV; `apply_review` moves nothing until a person writes `yes`
against a row — this is one batch of legacy cleanup, not a pipeline that runs
again next month. Applying reuses `merge.apply_merges` verbatim: move every
owner's coin, photograph and personal price snapshot onto the twin, archive the
orphan with the merge as its reason, delete it only once nothing references it
any more (docs/04-business-rules.md, rule 10) — the same order `merge.py` itself
already follows for the duplicates `gaps.py` makes.

Also worth recording here, since the same diagnosis turned it up: `is_active`
on `countries` is true for three rows, not only Ukraine (docs/02-data-model.md,
docs/BACKLOG.md) — unrelated to merging, left as a documentation fix, storefront
code untouched.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ukraine_pipeline import merge
from app.ukraine_pipeline.bridge import YES
from app.ukraine_pipeline.catalog import OurItem, load_items
from app.ukraine_pipeline.lexicon import Lexicon, strip_import_noise

CSV_COLUMNS = (
    "decision",
    "orphanId",
    "orphanTitle",
    "cleanedTitle",
    "instanceCount",
    # Up to MAX_CANDIDATES twins sharing the orphan's (year, denomination),
    # best first: "id:title:score" joined the way inventory-b's own
    # nbuCandidates column already is.
    "candidates",
    "suggestedTwinId",
    "suggestedAction",
)
MAX_CANDIDATES = 3
# A slot holds at most a handful of the National Bank's ~1000 cards — most
# years just one or two of a given denomination — so a lower floor than the
# open-search bridge/inventory-b use (55) does not run their false-match risk.
# Calibrated on the Mohyla/Desiatynna pair (module docstring): both clear it,
# neither clears bridge.REVIEW_THRESHOLD.
CANDIDATE_FLOOR = 35.0
# The top candidate must clearly lead the runner-up before the CSV suggests it
# outright — a close call is exactly the shape of "5 hryvnia 2018", a slot with
# several legitimate twins, and only a person should choose among those.
SUGGEST_MARGIN = 8.0
CIRCULATION_GROUP = "circulation"
NO_TWIN = "no-twin"
MERGE = "merge"
MANUAL = "manual"


def clean_orphan_title(title: str) -> str:
    """The orphan's own name, without the Excel heading and material tail.

    `lexicon.strip_import_noise` under a name a person reading this module can
    call and test on its own — see the module docstring for why the pattern it
    strips ("AgСеребро 0.925, 16.94g, ø 33mm") is the reason part B's bridge
    missed these pairs even though the pattern itself is not new.
    """
    return strip_import_noise(title) or title


@dataclass
class Candidate:
    twin: OurItem
    score: float


@dataclass
class OrphanRow:
    orphan: OurItem
    cleaned_title: str
    instance_count: int
    candidates: list[Candidate] = field(default_factory=list)
    suggested_twin_id: int | None = None
    suggested_action: str = MANUAL


@dataclass
class MergeBOutcome:
    rows: list[OrphanRow] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        for row in self.rows:
            by_action[row.suggested_action] = by_action.get(row.suggested_action, 0) + 1
        return {
            "orphans": len(self.rows),
            "withTwin": sum(1 for row in self.rows if row.candidates),
            "noTwin": by_action.get(NO_TWIN, 0),
            "suggestedMerge": by_action.get(MERGE, 0),
            "manual": by_action.get(MANUAL, 0),
        }


def is_orphan(item: OurItem) -> bool:
    """A record this tool may propose merging away: shared, active, not the
    circulation mini-pipeline's territory, and with no National Bank link at
    all — an NBU-linked record is either already correct or `merge.py`'s own
    job, not this one's.
    """
    return (
        not item.is_archived
        and item.collection_group != CIRCULATION_GROUP
        and not item.is_nbu_linked
    )


def is_twin(item: OurItem) -> bool:
    """A record this tool may propose merging an orphan *into*: shared,
    active, already the National Bank's own coin.
    """
    return not item.is_archived and item.is_nbu_linked


def _twins_by_slot(items: list[OurItem]) -> dict[tuple[int, int], list[OurItem]]:
    by_slot: dict[tuple[int, int], list[OurItem]] = {}
    for item in items:
        if is_twin(item) and item.denomination_id is not None:
            by_slot.setdefault((item.issue_year, item.denomination_id), []).append(item)
    return by_slot


def score_candidates(orphan: OurItem, twins: list[OurItem], lexicon: Lexicon) -> list[Candidate]:
    """Every twin of the orphan's own slot, best match first.

    Compared against both the twin's own-language title and its Ukrainian
    one: a record `gaps.py` created carries the National Bank's original
    spelling in `title_original`, but by the time `titles` has run against it
    (as it already has for every twin real enough to appear here) `title_uk`
    may say the same thing in the form a person actually reads.
    """
    cleaned = clean_orphan_title(orphan.title_original)
    scored = [
        Candidate(
            twin=twin,
            score=max(
                lexicon.score(cleaned, twin.title_original),
                lexicon.score(cleaned, twin.title_uk or ""),
            ),
        )
        for twin in twins
    ]
    scored.sort(key=lambda candidate: -candidate.score)
    return scored


def _suggest(candidates: list[Candidate]) -> tuple[str, int | None]:
    if not candidates:
        return NO_TWIN, None
    top = candidates[0]
    runner_up = candidates[1].score if len(candidates) > 1 else 0.0
    if top.score >= CANDIDATE_FLOOR and (top.score - runner_up) >= SUGGEST_MARGIN:
        return MERGE, top.twin.id
    return MANUAL, None


async def find_orphans(
    session: AsyncSession, *, country_id: int, lexicon: Lexicon
) -> MergeBOutcome:
    """One row per orphan, every twin its own (year, denomination) slot holds."""
    items = await load_items(session, country_id)
    twins_by_slot = _twins_by_slot(items)

    outcome = MergeBOutcome()
    for item in items:
        if not is_orphan(item):
            continue
        slot_twins = (
            []
            if item.denomination_id is None
            else twins_by_slot.get((item.issue_year, item.denomination_id), [])
        )
        candidates = score_candidates(item, slot_twins, lexicon)
        action, twin_id = _suggest(candidates)
        holdings = await merge.holdings_of(session, item.id)
        outcome.rows.append(
            OrphanRow(
                orphan=item,
                cleaned_title=clean_orphan_title(item.title_original),
                instance_count=holdings.instances,
                candidates=candidates[:MAX_CANDIDATES],
                suggested_twin_id=twin_id,
                suggested_action=action,
            )
        )
    return outcome


def write_review_csv(path: Path, outcome: MergeBOutcome) -> int:
    """One row per orphan; a person writes "yes" against the ones to merge."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.rows:
            writer.writerow(
                {
                    "decision": "",
                    "orphanId": row.orphan.id,
                    "orphanTitle": row.orphan.title_original,
                    "cleanedTitle": row.cleaned_title,
                    "instanceCount": row.instance_count,
                    "candidates": " | ".join(
                        f"{c.twin.id}:{c.twin.title_original}:{round(c.score, 1)}"
                        for c in row.candidates
                    ),
                    "suggestedTwinId": row.suggested_twin_id or "",
                    "suggestedAction": row.suggested_action,
                }
            )
    return len(outcome.rows)


def read_review_csv(path: Path) -> list[tuple[int, int]]:
    """[(twin id to keep, orphan id to retire)] out of the rows marked yes.

    Handed straight to `merge.apply_merges` — this file only decides which
    pairs to move, not how. A row marked yes with no `suggestedTwinId` (a
    `manual`/`no-twin` row a person answered "yes" on without picking a twin)
    is refused: a chosen twin belongs in that column, not implied by a bare
    "yes". Opened as utf-8-sig for the same reason `merge.read_merge_csv` is —
    a person reviews this in Excel.
    """
    chosen: list[tuple[int, int]] = []
    seen: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() not in YES:
                continue
            orphan_id = int(str(row["orphanId"]).strip())
            twin_raw = (row.get("suggestedTwinId") or "").strip()
            if not twin_raw:
                message = f"merge-b file marks orphan #{orphan_id} yes with no suggestedTwinId"
                raise ValueError(message)
            twin_id = int(twin_raw)
            if orphan_id == twin_id:
                message = f"merge-b file pairs record #{orphan_id} with itself"
                raise ValueError(message)
            if orphan_id in seen or twin_id in seen:
                dupe = orphan_id if orphan_id in seen else twin_id
                message = f"merge-b file names record #{dupe} twice"
                raise ValueError(message)
            seen.update((orphan_id, twin_id))
            chosen.append((twin_id, orphan_id))
    return chosen
