"""Orchestration: which step runs, in what order, in whose transaction.

Steps are independent and each is safe to run twice. The order below is the
order of dependency, and it is the order of the runbook in backend/README.md:

    bridge -> series -> gaps -> repair-gaps -> merge -> titles -> photos -> prices

bridge decides which of our records is which coin; everything after it works
from those links, read back out of the database rather than passed along, so a
step can be run days later on its own.

repair-gaps and merge clean up after an earlier run of gaps: the first fills
in the columns it left empty, the second lists the records it duplicated. Both
are ordinary steps and both are safe to run when there is nothing to do.
merge only writes when it is handed a reviewed file with --apply-merge.

Each step commits on its own. A failure while downloading eight gigabytes of
photographs must not undo the names.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import ObjectStorage
from app.models import Currency
from app.ukraine_pipeline import (
    bridge,
    circ_bridge,
    circ_gaps,
    circ_inventory,
    circ_mintage,
    circ_photos,
    circ_reclassify,
    circ_titles,
    circ_variants,
    gaps,
    jubilee_bridge,
    merge,
    merge_b,
    photos,
    prices,
    repair,
    series,
    titles,
    translate_c,
)
from app.ukraine_pipeline.catalog import OurItem, load_items, ukraine_country_id
from app.ukraine_pipeline.lexicon import Lexicon, load_lexicon
from app.ukraine_pipeline.report import PipelineReport
from app.ukraine_pipeline.sources import Sources, cluster_key
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCES
from app.ukraine_recon.triangulate import Cluster
from app.ukraine_recon.wikipedia import MintageCell

# series before gaps on purpose: gaps creates records under the NBU series
# names, and renaming ours afterwards would collide with what it just made.
COMMEMORATIVE_STEPS = (
    "bridge",
    "series",
    "gaps",
    "repair-gaps",
    "merge",
    "titles",
    "photos",
    "prices",
)
# The circulation mini-pipeline (docs/05-integrations.md, "обиходные монеты").
# Independent of the steps above — a different bridge, a different source
# (the Wikipedia mintage table, not the three commemorative sources) — but
# ordered the same way: link first, fill what is missing, then names, numbers
# and photographs. circ-reclassify runs before any of that: `circulation` is
# contaminated by the legacy groupFor heuristic (docs/04-business-rules.md,
# rule 11) with commemoratives the NBU catalogue already links, and no step
# after it may treat those as ordinary circulation coins.
CIRCULATION_STEPS = (
    "circ-reclassify",
    "circ-bridge",
    # Right after circ-bridge, before circ-gaps: a duplicate this step
    # retires must already know which of its slot-mates is the linked base
    # (circ-bridge's own job), and circ-gaps must not mistake a slot a
    # duplicate still occupies for an empty one (docs/05-integrations.md,
    # section 10 — though in practice the base already occupies the slot
    # either way, so there is no real ordering hazard, only a logical one).
    "circ-variants",
    "circ-gaps",
    "circ-titles",
    "circ-mintage",
    "circ-photos",
)
# One-off tools for the remainder of the catalogue (docs/05-integrations.md,
# section 10 continuation): a targeted NBU match for six specific
# mispatriated jubilee records, a self-to-self merge of the legacy Excel
# remainder that already has a twin in our own catalogue (section 10's
# "merge-b" subsection), and a survey CSV of whatever is left genuinely
# unlinked afterwards. merge-b runs before inventory-b on purpose: every pair
# it merges away is one fewer row for inventory-b to survey. Independent of
# the ordered chains above and of each other otherwise — any of the three can
# run alone — but grouped at the end of STEPS so `--steps` with no argument
# still runs everything once.
EXTRA_STEPS = ("jubilee-bridge", "merge-b", "inventory-b")
# LLM translation of whatever the steps above still left without an official
# name (docs/05-integrations.md, part C) — no Sources, no NBU/ua-coins/Wikipedia
# fetch, entirely independent of everything above. Last on purpose: it should
# only ever see the genuine remainder, not a record another step would have
# named for free this same run.
TRANSLATE_STEPS = ("translate-c",)
STEPS = COMMEMORATIVE_STEPS + CIRCULATION_STEPS + EXTRA_STEPS + TRANSLATE_STEPS


class PipelineError(Exception):
    """Something the run cannot continue without."""


async def _unreachable_translate(_tasks: object) -> None:
    """Placeholder passed to translate_c when call_api is False — never invoked."""
    message = "translate-c: translate() called without call_api"
    raise PipelineError(message)


@dataclass
class Options:
    steps: tuple[str, ...] = STEPS
    dry_run: bool = True
    limit: int | None = None
    review_out: Path | None = None
    review_in: Path | None = None
    duplicates_out: Path | None = None
    merge_out: Path | None = None
    merge_in: Path | None = None
    # Separate from review_out/review_in: circ-bridge's ambiguous rows are a
    # different shape (docs/05-integrations.md), and running bridge and
    # circ-bridge together must not have one overwrite the other's file.
    circ_review_out: Path | None = None
    circ_review_in: Path | None = None
    report_path: Path | None = None
    # circ-photos only: type keys (app/ukraine_pipeline/circ_types.py) whose
    # already-stored `nbu` images should be deleted and re-fetched instead of
    # left alone by the step's usual idempotency — see circ_photos.py.
    circ_refresh_types: frozenset[str] = field(default_factory=frozenset)
    # circ-mintage only: recompute and overwrite mintage_actual on every
    # non-NBU-linked circulation record instead of only filling empty ones —
    # see circ_mintage.py's module docstring.
    circ_refresh_mintage: bool = False
    # circ-variants: its own review file, apart from --review-out/-in and
    # --circ-review-out/-in — a different shape again (docs/05-integrations.md).
    circ_variants_review_out: Path | None = None
    circ_variants_review_in: Path | None = None
    # jubilee-bridge: one CSV, own flag pair.
    jubilee_review_out: Path | None = None
    jubilee_review_in: Path | None = None
    # inventory-b: writes with --inventory-out; a `link` decision is applied
    # back with --apply-inventory-review, read the same way jubilee-bridge's
    # own review file is (see app/ukraine_pipeline/circ_inventory.py).
    inventory_out: Path | None = None
    inventory_review_in: Path | None = None
    # merge-b: its own review file, applied through merge.apply_merges itself
    # (see app/ukraine_pipeline/merge_b.py) — a separate pair of flags from
    # --merge-out/--apply-merge, which is merge.py's own CSV for the
    # duplicates gaps.py makes, a different shape of pair entirely.
    merge_b_out: Path | None = None
    merge_b_in: Path | None = None
    # translate-c: where to write the (id, old original, new uk/en) review CSV.
    # Passing it on a dry run is the one exception to "dry run never calls the
    # API" — see app/ukraine_pipeline/translate_c.py's module docstring.
    translate_out: Path | None = None


@dataclass
class Runner:
    session: AsyncSession
    client: PoliteClient
    sources: Sources
    report: PipelineReport
    options: Options
    log: Callable[[str], None]
    storage: ObjectStorage | None = None
    # translate-c's one call-out; None means the step cannot reach the API —
    # fine on a plain dry run, an error if --apply or --translate-out asks for
    # it anyway (scripts/ukraine_pipeline.py checks this before the run starts).
    translate: translate_c.TranslateFn | None = None
    lexicon: Lexicon = field(default_factory=load_lexicon)
    # The Wikipedia mintage table, fetched separately from `sources` above —
    # a different page, needed only by the circ-* steps. Empty unless one of
    # them was requested (scripts/ukraine_pipeline.py fetches it lazily).
    mintage: list[MintageCell] = field(default_factory=list)

    _country_id: int | None = None
    _items: list[OurItem] = field(default_factory=list)
    # What the bridge decided in this run. A dry run writes no links, so
    # without this the steps after it would see only the links that were
    # already in the database and report almost nothing.
    _bridge_pairs: dict[int, Cluster] = field(default_factory=dict)

    async def run(self) -> PipelineReport:
        self._country_id = await ukraine_country_id(self.session)
        if self._country_id is None:
            message = "no Ukraine in the countries table; run the migrations first"
            raise PipelineError(message)
        await self._load_catalog()

        for step in STEPS:
            if step in self.options.steps:
                await getattr(self, f"_step_{step.replace('-', '_')}")()
        return self.report

    async def _load_catalog(self) -> None:
        assert self._country_id is not None
        self._items = await load_items(self.session, self._country_id)
        self.report.catalog = {
            "countryId": self._country_id,
            "items": len(self._items),
            "commemorative": sum(1 for item in self._items if item.is_commemorative),
            "circulation": sum(1 for item in self._items if not item.is_commemorative),
            "archived": sum(1 for item in self._items if item.is_archived),
        }
        self.log(f"catalogue: {len(self._items)} shared Ukrainian records")

    async def _commit(self) -> None:
        if self.options.dry_run:
            await self.session.rollback()
        else:
            await self.session.commit()

    # ------------------------------------------------------------------ steps
    async def _step_bridge(self) -> None:
        outcome = bridge.decide(self._items, self.sources, self.lexicon)
        problems: list[str] = []
        if self.options.review_in is not None:
            decisions = bridge.read_review_csv(self.options.review_in)
            outcome, problems = bridge.apply_review(outcome, decisions, self.sources)
            self.log(f"review: {len(decisions)} decisions read from {self.options.review_in}")
        for problem in problems:
            self.report.warn(f"bridge review: {problem}")

        written = 0
        if not self.options.dry_run:
            written = await bridge.write_links(self.session, outcome)
        rows = 0
        if self.options.review_out is not None and outcome.review:
            rows = bridge.write_review_csv(self.options.review_out, outcome)
            self.log(f"review: {rows} candidate rows written to {self.options.review_out}")

        self._bridge_pairs = {
            decision.item.id: decision.cluster
            for decision in outcome.linked
            if decision.cluster is not None
        }
        self.report.step(
            "bridge",
            {**outcome.summary(), "linkRowsWritten": written, "reviewRowsWritten": rows},
            examples=[
                {
                    "itemId": decision.item.id,
                    "ourTitle": decision.item.title_original,
                    "cluster": cluster_key(decision.cluster) if decision.cluster else None,
                    "score": round(decision.score, 1),
                    "strategy": decision.strategy,
                }
                for decision in outcome.linked[:20]
            ],
            withoutCandidates=[
                {"itemId": item.id, "title": item.title_original, "year": item.issue_year}
                for item in outcome.without_candidates[:50]
            ],
        )
        await self._commit()

    async def _step_gaps(self) -> None:
        assert self._country_id is not None
        pairs = await self._linked_clusters()
        linked_keys = {cluster_key(cluster) for cluster in pairs.values()}
        outcome = await gaps.create_missing(
            self.session,
            country_id=self._country_id,
            sources=self.sources,
            linked_keys=linked_keys,
            dry_run=self.options.dry_run,
            lexicon=self.lexicon,
            items=self._items,
            linked_ids=set(pairs),
            limit=self.options.limit,
        )
        rows = 0
        if self.options.duplicates_out is not None and outcome.would_duplicate:
            rows = gaps.write_duplicates_csv(self.options.duplicates_out, outcome)
            self.log(f"gaps: {rows} would-duplicate rows written to {self.options.duplicates_out}")
        self.report.step(
            "gaps",
            {**outcome.summary(), "duplicateRowsWritten": rows},
            created=outcome.created[:50],
            wouldDuplicate=outcome.would_duplicate[:50],
        )
        for problem in outcome.problems:
            self.report.warn(f"gaps: {problem}")
        await self._commit()
        await self._load_catalog()

    async def _step_repair_gaps(self) -> None:
        assert self._country_id is not None
        outcome = await repair.repair_gaps(
            self.session,
            country_id=self._country_id,
            sources=self.sources,
            dry_run=self.options.dry_run,
        )
        self.report.step(
            "repair-gaps",
            outcome.summary(),
            examples=outcome.examples,
            withoutCard=outcome.without_card[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_merge(self) -> None:
        """Lists the duplicates; moves nothing unless handed a reviewed file."""
        assert self._country_id is not None
        outcome = await merge.find_pairs(
            self.session,
            country_id=self._country_id,
            sources=self.sources,
            lexicon=self.lexicon,
        )
        rows = 0
        if self.options.merge_out is not None and outcome.candidates:
            rows = merge.write_merge_csv(self.options.merge_out, outcome)
            self.log(f"merge: {rows} candidate pairs written to {self.options.merge_out}")

        applied = merge.MergeOutcome()
        if self.options.merge_in is not None:
            decisions = merge.read_merge_csv(self.options.merge_in)
            self.log(f"merge: {len(decisions)} decisions read from {self.options.merge_in}")
            applied = await merge.apply_merges(
                self.session, decisions, dry_run=self.options.dry_run
            )
        for problem in applied.problems:
            self.report.warn(f"merge: {problem}")
        self.report.step(
            "merge",
            {**outcome.summary(), **applied.summary(), "candidateRowsWritten": rows},
            candidates=outcome.candidates[:50],
            merged=applied.merged[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_titles(self) -> None:
        pairs = await self._linked_clusters()
        outcome = await titles.apply_titles(
            self.session,
            pairs=pairs,
            sources=self.sources,
            lexicon=self.lexicon,
            dry_run=self.options.dry_run,
        )
        self.report.step(
            "titles",
            outcome.summary(),
            examples=outcome.examples,
            disagreements=outcome.disagreements[:50],
        )
        await self._commit()

    async def _step_series(self) -> None:
        assert self._country_id is not None
        outcome = await series.rename_series(
            self.session,
            country_id=self._country_id,
            nbu_records=self.sources.nbu,
            nbu_english=self.sources.nbu_english,
            dry_run=self.options.dry_run,
        )
        self.report.step(
            "series",
            outcome.summary(),
            renamed=outcome.renamed,
            detached=outcome.detached,
            unmapped=outcome.unmapped,
        )
        await self._commit()

    async def _step_photos(self) -> None:
        pairs = await self._linked_clusters()
        outcome = await photos.download_photos(
            self.session,
            client=self.client,
            storage=self.storage,
            pairs=pairs,
            sources=self.sources,
            dry_run=self.options.dry_run,
            limit=self.options.limit,
            log=self.log,
        )
        self.report.step(
            "photos",
            outcome.summary(),
            failed=outcome.failed[:50],
            itemsWithoutAnyImage=outcome.without_source[:50],
        )
        await self._commit()

    async def _step_prices(self) -> None:
        pairs = await self._linked_clusters()
        currencies = list((await self.session.execute(select(Currency.code))).scalars().all())
        outcome = await prices.record_prices(
            self.session, pairs=pairs, currencies=currencies, dry_run=self.options.dry_run
        )
        self.report.step("prices", outcome.summary(), examples=outcome.examples)
        await self._commit()

    # ---------------------------------------------------------- circulation
    async def _step_circ_reclassify(self) -> None:
        outcome = await circ_reclassify.apply_reclassify(
            self.session, items=self._items, dry_run=self.options.dry_run
        )
        self.report.step(
            "circ-reclassify",
            outcome.summary(),
            reclassified=outcome.reclassified[:50],
            officialWithoutNbuLink=outcome.official_without_nbu_link[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_circ_bridge(self) -> None:
        assert self._country_id is not None
        outcome = await circ_bridge.run_bridge(
            self.session,
            country_id=self._country_id,
            items=self._items,
            mintage=self.mintage,
            dry_run=self.options.dry_run,
        )
        if self.options.circ_review_in is not None:
            path = self.options.circ_review_in
            decisions = circ_bridge.read_review_csv(path)
            outcome = circ_bridge.apply_review(outcome, decisions)
            self.log(f"circ-bridge review: {len(decisions)} decisions read from {path}")
        rows = 0
        if not self.options.dry_run:
            rows = await circ_bridge.write_links(self.session, outcome.linked)
        review_rows = 0
        if self.options.circ_review_out is not None and outcome.review:
            review_rows = circ_bridge.write_review_csv(self.options.circ_review_out, outcome)
            self.log(
                f"circ-bridge: {review_rows} review rows written to {self.options.circ_review_out}"
            )
        self.report.step(
            "circ-bridge",
            {**outcome.summary(), "linkRowsWritten": rows, "reviewRowsWritten": review_rows},
            denominationsUnparsed=outcome.repaired.unparsed[:50],
            withoutWikipediaEntry=[
                {"itemId": item.id, "title": item.title_original, "year": item.issue_year}
                for item in outcome.without_wikipedia_entry[:50]
            ],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_circ_variants(self) -> None:
        outcome = await circ_variants.run_variants(
            self.session, items=self._items, dry_run=self.options.dry_run
        )
        applied = circ_variants.CircVariantsOutcome()
        if self.options.circ_variants_review_in is not None:
            path = self.options.circ_variants_review_in
            decisions = circ_variants.read_review_csv(path)
            applied = await circ_variants.apply_review(
                self.session, decisions, dry_run=self.options.dry_run
            )
            self.log(f"circ-variants review: {len(decisions)} decisions read from {path}")
        rows = 0
        if self.options.circ_variants_review_out is not None and outcome.review:
            rows = circ_variants.write_review_csv(self.options.circ_variants_review_out, outcome)
            self.log(
                f"circ-variants: {rows} review rows written to "
                f"{self.options.circ_variants_review_out}"
            )
        self.report.step(
            "circ-variants",
            {**outcome.summary(), "reviewApplied": len(applied.created), "reviewRowsWritten": rows},
            created=(outcome.created + applied.created)[:50],
            subtypesAssigned=outcome.subtypes_assigned[:50],
            personalInstancesOnVariant=(
                outcome.personal_instances_on_variant + applied.personal_instances_on_variant
            )[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_circ_gaps(self) -> None:
        assert self._country_id is not None
        outcome = await circ_gaps.create_missing(
            self.session,
            country_id=self._country_id,
            items=self._items,
            mintage=self.mintage,
            dry_run=self.options.dry_run,
        )
        self.report.step(
            "circ-gaps",
            outcome.summary(),
            created=outcome.created[:50],
            skippedNoType=outcome.skipped_no_type[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_circ_titles(self) -> None:
        assert self._country_id is not None
        outcome = await circ_titles.apply_titles(
            self.session, country_id=self._country_id, dry_run=self.options.dry_run
        )
        self.report.step("circ-titles", outcome.summary(), examples=outcome.examples)
        await self._commit()

    async def _step_circ_mintage(self) -> None:
        assert self._country_id is not None
        outcome = await circ_mintage.apply_mintage(
            self.session,
            country_id=self._country_id,
            mintage=self.mintage,
            dry_run=self.options.dry_run,
            refresh=self.options.circ_refresh_mintage,
        )
        self.report.step(
            "circ-mintage",
            outcome.summary(),
            ambiguous=outcome.ambiguous[:50],
            discrepancies=outcome.discrepancies[:50],
            refreshed=outcome.refreshed[:50],
        )
        await self._commit()

    async def _step_circ_photos(self) -> None:
        assert self._country_id is not None
        outcome = await circ_photos.download_photos(
            self.session,
            client=self.client,
            storage=self.storage,
            country_id=self._country_id,
            dry_run=self.options.dry_run,
            limit=self.options.limit,
            log=self.log,
            refresh_types=self.options.circ_refresh_types,
        )
        self.report.step(
            "circ-photos",
            outcome.summary(),
            failed=outcome.failed[:50],
        )
        await self._commit()

    # ------------------------------------------------------------------ extra
    async def _step_jubilee_bridge(self) -> None:
        outcome = jubilee_bridge.find_candidates(
            self.client, items=self._items, lexicon=self.lexicon, log=self.log
        )
        written = 0
        if self.options.jubilee_review_in is not None:
            path = self.options.jubilee_review_in
            decisions = jubilee_bridge.read_review_csv(path)
            if not self.options.dry_run:
                written = await jubilee_bridge.write_links(self.session, decisions)
            self.log(f"jubilee-bridge: {len(decisions)} decisions read from {path}")
        rows = 0
        if self.options.jubilee_review_out is not None and outcome.review:
            rows = jubilee_bridge.write_review_csv(self.options.jubilee_review_out, outcome)
            self.log(
                f"jubilee-bridge: {rows} review rows written to {self.options.jubilee_review_out}"
            )
        self.report.step(
            "jubilee-bridge",
            {**outcome.summary(), "linkRowsWritten": written, "reviewRowsWritten": rows},
            noCandidates=outcome.no_candidates[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_merge_b(self) -> None:
        """Lists the orphan/twin pairs; moves nothing unless handed a reviewed file."""
        assert self._country_id is not None
        outcome = await merge_b.find_orphans(
            self.session, country_id=self._country_id, lexicon=self.lexicon
        )
        rows = 0
        if self.options.merge_b_out is not None and outcome.rows:
            rows = merge_b.write_review_csv(self.options.merge_b_out, outcome)
            self.log(f"merge-b: {rows} orphan rows written to {self.options.merge_b_out}")

        applied = merge.MergeOutcome()
        if self.options.merge_b_in is not None:
            decisions = merge_b.read_review_csv(self.options.merge_b_in)
            self.log(f"merge-b: {len(decisions)} decisions read from {self.options.merge_b_in}")
            applied = await merge.apply_merges(
                self.session, decisions, dry_run=self.options.dry_run
            )
        for problem in applied.problems:
            self.report.warn(f"merge-b: {problem}")
        self.report.step(
            "merge-b",
            {**outcome.summary(), **applied.summary(), "csvRowsWritten": rows},
            merged=applied.merged[:50],
        )
        await self._commit()
        await self._load_catalog()

    async def _step_inventory_b(self) -> None:
        outcome = circ_inventory.build_inventory(self._items, self.sources, self.lexicon)
        rows = 0
        if self.options.inventory_out is not None and outcome.rows:
            rows = circ_inventory.write_csv(self.options.inventory_out, outcome)
            self.log(f"inventory-b: {rows} rows written to {self.options.inventory_out}")
        written = 0
        if self.options.inventory_review_in is not None:
            path = self.options.inventory_review_in
            decisions = jubilee_bridge.read_review_csv(path)
            if not self.options.dry_run:
                written = await jubilee_bridge.write_links(self.session, decisions)
            self.log(f"inventory-b: {len(decisions)} link decisions read from {path}")
        self.report.step(
            "inventory-b", {**outcome.summary(), "csvRowsWritten": rows, "linkRowsWritten": written}
        )
        await self._commit()
        await self._load_catalog()

    # -------------------------------------------------------------- translate
    async def _step_translate_c(self) -> None:
        assert self._country_id is not None
        call_api = not self.options.dry_run or self.options.translate_out is not None
        if call_api and self.translate is None:
            message = "translate-c needs the Anthropic API but no key is configured"
            raise PipelineError(message)
        outcome = await translate_c.run_translate_c(
            self.session,
            country_id=self._country_id,
            # call_api already guards the None case; a plain dry run never calls this.
            translate=self.translate or _unreachable_translate,
            dry_run=self.options.dry_run,
            call_api=call_api,
        )
        rows = 0
        if self.options.translate_out is not None and outcome.rows:
            rows = translate_c.write_review_csv(self.options.translate_out, outcome)
            self.log(f"translate-c: {rows} rows written to {self.options.translate_out}")
        for problem in outcome.errors:
            self.report.warn(f"translate-c: batch {problem['ids']} — {problem['reason']}")
        self.report.step(
            "translate-c", {**outcome.summary(), "csvRowsWritten": rows}, errors=outcome.errors[:50]
        )
        await self._commit()
        await self._load_catalog()

    # -------------------------------------------------------------- internals
    async def _linked_clusters(self) -> dict[int, Cluster]:
        """{item id: cluster} from the links the bridge step wrote.

        Read back from the database on purpose: that is what lets a later step
        run in its own session, days after the bridge, without being handed
        anything.
        """
        item_ids = [item.id for item in self._items]
        links = await bridge.linked_pairs(self.session, item_ids)
        pairs: dict[int, Cluster] = dict(self._bridge_pairs)
        for item in self._items:
            # The source key counts as a reference too, and the rows the
            # bridge wrote in this run outrank the ones the catalogue was
            # loaded with.
            by_source = {**item.links, **links.get(item.id, {})}
            for source in SOURCES:
                cluster = bridge.cluster_of_reference(
                    self.sources, source, by_source.get(source, "")
                )
                if cluster is not None:
                    pairs[item.id] = cluster
                    break
        return pairs


def parse_steps(value: str | None) -> tuple[str, ...]:
    if not value:
        return STEPS
    chosen = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [step for step in chosen if step not in STEPS]
    if unknown:
        message = f"unknown steps: {', '.join(unknown)}; known: {', '.join(STEPS)}"
        raise PipelineError(message)
    return chosen


def source_summary(sources: Sources) -> dict[str, Any]:
    return {
        name: {"records": len(records), "access": sources.access.get(name, "?")}
        for name, records in sources.by_source().items()
    }
