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
from app.ukraine_pipeline import bridge, gaps, merge, photos, prices, repair, series, titles
from app.ukraine_pipeline.catalog import OurItem, load_items, ukraine_country_id
from app.ukraine_pipeline.lexicon import Lexicon, load_lexicon
from app.ukraine_pipeline.report import PipelineReport
from app.ukraine_pipeline.sources import Sources, cluster_key
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCES
from app.ukraine_recon.triangulate import Cluster

# series before gaps on purpose: gaps creates records under the NBU series
# names, and renaming ours afterwards would collide with what it just made.
STEPS = (
    "bridge",
    "series",
    "gaps",
    "repair-gaps",
    "merge",
    "titles",
    "photos",
    "prices",
)


class PipelineError(Exception):
    """Something the run cannot continue without."""


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
    report_path: Path | None = None


@dataclass
class Runner:
    session: AsyncSession
    client: PoliteClient
    sources: Sources
    report: PipelineReport
    options: Options
    log: Callable[[str], None]
    storage: ObjectStorage | None = None
    lexicon: Lexicon = field(default_factory=load_lexicon)

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
