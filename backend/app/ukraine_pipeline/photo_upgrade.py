"""photo-upgrade — the general mechanism scan_coin_photo_packaging.py's first
wave (2026-09-08) led to: no title-matching, no per-record classification of
"is this packaging" ahead of time. A record has a known ua-coins.info page ->
every photo-candidate its gallery offers is pulled and ranked
(classify_coin_photos.py) -> the best candidate replaces the stored photo
only when it confidently beats it. Worse than the status quo cannot happen by
construction: a record with no confident winner is left exactly as it was.

Candidates are the shared, active Ukrainian records `bridge.py` (or an older
run's price_source_links row) already points at a ua-coins.info page for —
`price_source_links.source = "UA-Coins"`, `external_id` an absolute URL. A
record with no such row is counted, not scanned (`without_page`); this is
deliberately narrower than "every record ua-coins.info might have a page
for" — that would need the same year/denomination/title matching `bridge.py`
already does, and duplicating it here is not the point.

Three-tier obverse/reverse pick per record (`pick_roles`):

1. metadata — a gallery image's `alt` or filename already says "obverse"/
   "reverse" (or the Ukrainian/Russian "аверс"/"реверс"); trusted outright,
   no geometry needed. `parse_regular_ua_detail`'s own two hand-picked images
   are exactly this case, generalised to an arbitrary gallery.
2. geometry — a role metadata left unresolved is filled from whatever
   gallery images remain, ranked by `classify_coin_photos.score` the same
   way `pick_best` ranks a page (best-scoring coin-shaped image first).
3. fallback — nothing is left to fill a role with; the record is reported
   flagged, not replaced. A record whose stored photo already covers a role
   with no resolvable candidate for it is left alone rather than having that
   role's photo deleted with nothing to put back
   (`app/ukraine_pipeline/photo_replace.py`).

Replacing at all still needs a *confident* win (`should_replace`) over the
combined (worst-of-both-sides, `classify_coin_photos.combine`) score of what
is already stored — this is what protects a figural coin (Писанка,
Пектораль): its own gallery photos are exactly as "non-circular" as its
stored one, so no confident win, no replacement, no special-casing needed.

Traversal is a single streaming pass (2026-09-08 fix, after an OOM on the
3.7 GiB production box at ~1300 records): `run()` looks at one record at a
time — fetch its gallery, score it, compare, optionally write a CSV row and
apply, then move on. Nothing from one record's images or verdicts survives
into the next iteration, and every accumulator the report is built from is a
`BoundedList` (a fixed-size sample plus a count) rather than a list that
grows with the size of the catalogue — see its own docstring.
"""

from __future__ import annotations

import csv
import re
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.images import MAX_SOURCE_BYTES
from app.core.storage import ObjectStorage
from app.models import CatalogItem, PriceSourceLink
from app.ukraine_pipeline import photo_replace
from app.ukraine_pipeline.catalog import LINK_SOURCES
from app.ukraine_pipeline.classify_coin_photos import Verdict, classify, combine, score
from app.ukraine_recon import ua_coins
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCE_UA_COINS
from app.ukraine_recon.ua_coins import GalleryImage

ROLES = photo_replace.ROLES
_ROLE_PATTERNS = {
    "obverse": re.compile(r"obverse|аверс", re.IGNORECASE),
    "reverse": re.compile(r"reverse|реверс", re.IGNORECASE),
}

# "Confident win" over the currently stored photo (score() range is ~0..1).
# Either the candidate is clearly good and the current one clearly is not, or
# the gap between them is wide enough that a middling current photo is still
# worth replacing — but never a marginal wobble between two mediocre photos
# (CANDIDATE_FLOOR keeps the gap branch from firing on two bad scores).
CANDIDATE_MIN = 0.85
CURRENT_MAX = 0.65
GAP_MIN = 0.25
CANDIDATE_FLOOR = 0.70

# How many example rows the report keeps for fallbacks/failures/replacements/
# duplicate-title groups — a constant, not a fraction of the catalogue, so
# the report itself cannot be the thing that grows with N (BoundedList).
SAMPLE_LIMIT = 50

YES = frozenset({"y", "yes", "1", "true", "+", "так"})
CSV_COLUMNS = (
    "decision",
    "itemId",
    "title",
    "year",
    "currentScore",
    "candidateScore",
    "tier",
    "obverseUrl",
    "reverseUrl",
    "note",
)


def should_replace(current_score: float, candidate_score: float) -> bool:
    if candidate_score >= CANDIDATE_MIN and current_score <= CURRENT_MAX:
        return True
    return candidate_score >= CANDIDATE_FLOOR and candidate_score - current_score >= GAP_MIN


# ------------------------------------------------------------- role picking
@dataclass(frozen=True, slots=True)
class RolePick:
    image: GalleryImage
    tier: str  # "metadata" | "geometry"


def _role_of(image: GalleryImage) -> str | None:
    text = f"{image.alt} {image.filename}"
    for role, pattern in _ROLE_PATTERNS.items():
        if pattern.search(text):
            return role
    return None


def pick_roles_by_metadata(images: Sequence[GalleryImage]) -> dict[str, RolePick]:
    """Tier 1, pure: every role a gallery image's own alt/filename already
    names, first match in page order wins. No image bytes involved."""
    picks: dict[str, RolePick] = {}
    for image in images:
        role = _role_of(image)
        if role is not None and role not in picks:
            picks[role] = RolePick(image=image, tier="metadata")
    return picks


def pick_roles(images: Sequence[GalleryImage], verdicts: dict[str, Verdict]) -> dict[str, RolePick]:
    """Tiers 1 and 2 together. `verdicts` is keyed by `GalleryImage.url` for
    every image tier 2 might need to rank — tier 3 (nothing left to assign)
    is simply the role staying absent from the result."""
    picks = pick_roles_by_metadata(images)
    used = {pick.image.url for pick in picks.values()}
    remaining = [image for image in images if image.url not in used and image.url in verdicts]
    missing = [role for role in ROLES if role not in picks]
    if missing and remaining:

        def _rank(image: GalleryImage) -> tuple[bool, float, int]:
            verdict = verdicts[image.url]
            return (not verdict.is_coin, -score(verdict), image.order)

        ranked = sorted(remaining, key=_rank)
        for role, image in zip(missing, ranked, strict=False):
            picks[role] = RolePick(image=image, tier="geometry")
    return picks


# ------------------------------------------------------------------ per-item
@dataclass
class ItemDiff:
    item_id: int
    title: str
    year: int
    current_score: float
    candidate_score: float
    tier: str
    obverse_url: str | None
    reverse_url: str | None
    note: str = "ok"


async def candidate_items(
    session: AsyncSession, *, country_id: int
) -> list[tuple[int, str, int, str]]:
    """(item_id, title_original, issue_year, ua-coins.info page URL) for every
    shared, active Ukrainian record a link already names an absolute URL for.

    Only the four scalar columns actually used below — never the full ORM
    entity, and never a relationship — so materialising this list for an
    order-1000 catalogue costs kilobytes, not the megabytes a widish row
    class multiplies into. Bare legacy ids (no slug, no URL) cannot be turned
    into a fetchable page without guessing at one, so they fall out of this —
    into `without_page`, not treated as a page we know.
    """
    rows = await session.execute(
        select(
            CatalogItem.id,
            CatalogItem.title_original,
            CatalogItem.issue_year,
            PriceSourceLink.external_id,
        )
        .join(PriceSourceLink, PriceSourceLink.catalog_item_id == CatalogItem.id)
        .where(
            CatalogItem.country_id == country_id,
            CatalogItem.created_by.is_(None),
            CatalogItem.is_archived.is_(False),
            PriceSourceLink.source == LINK_SOURCES[SOURCE_UA_COINS],
            PriceSourceLink.external_id.like("http%"),
        )
        .order_by(CatalogItem.id)
    )
    return [(item_id, title, year, url) for item_id, title, year, url in rows.all()]


async def _title_year_rows(session: AsyncSession, *, country_id: int) -> list[tuple[int, str, int]]:
    rows = await session.execute(
        select(CatalogItem.id, CatalogItem.title_original, CatalogItem.issue_year).where(
            CatalogItem.country_id == country_id,
            CatalogItem.created_by.is_(None),
            CatalogItem.is_archived.is_(False),
        )
    )
    return [(item_id, title, year) for item_id, title, year in rows.all()]


def find_duplicate_titles(rows: Sequence[tuple[int, str, int]]) -> list[dict[str, Any]]:
    """(item_id, title_original, issue_year) rows grouped by title+year, kept
    only where 2+ active records share one — a report-only addendum
    (docs/BACKLOG.md decides what, if anything, to do about it). Takes the
    same lightweight rows `_title_year_rows` reads, not full catalog entities
    and not anything the photo walk itself touches.
    """
    groups: dict[tuple[str, int], list[int]] = {}
    for item_id, title, year in rows:
        groups.setdefault((title, year), []).append(item_id)
    return [
        {"titleOriginal": title, "issueYear": year, "itemIds": sorted(ids)}
        for (title, year), ids in sorted(groups.items())
        if len(ids) >= 2
    ]


def _suffix_of(url: str) -> str:
    return Path(url.split("?", 1)[0]).suffix or ".img"


def _classify_url(client: PoliteClient, url: str) -> Verdict | None:
    """Download, classify, discard: `payload` and, inside `classify()`, the
    decoded image array both go out of scope with this call — only the small
    `Verdict` survives it, so a caller looping over many records never holds
    more than one record's bytes at a time."""
    _result, payload = client.get_range(url, MAX_SOURCE_BYTES)
    if not payload:
        return None
    with tempfile.NamedTemporaryFile(suffix=_suffix_of(url)) as handle:
        handle.write(payload)
        handle.flush()
        return classify(Path(handle.name))


def _classify_stored(storage: ObjectStorage, storage_key: str | None) -> Verdict:
    assert storage_key is not None  # official_photos()'s own query filters this
    payload = storage.get(storage_key)
    with tempfile.NamedTemporaryFile(suffix=".webp") as handle:
        handle.write(payload)
        handle.flush()
        return classify(Path(handle.name))


async def _diff_for_item(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    item_id: int,
    title: str,
    year: int,
    url: str,
) -> ItemDiff | dict[str, Any] | None:
    current = await photo_replace.official_photos(session, item_id)
    roles_present = [role for role in ROLES if role in current]
    if not roles_present:
        return None  # nothing stored yet for this record — out of scope here

    page = client.get(url)
    if not page.ok:
        return {
            "itemId": item_id,
            "title": title,
            "reason": f"page unreachable: HTTP {page.status}",
        }
    images = ua_coins.parse_coin_gallery(page.text)
    if not images:
        return {
            "itemId": item_id,
            "title": title,
            "reason": "no gallery images found on the page",
        }

    verdicts: dict[str, Verdict] = {}
    for image in images:
        verdict = _classify_url(client, image.url)
        if verdict is not None:
            verdicts[image.url] = verdict

    picks = pick_roles(images, verdicts)
    missing = [role for role in roles_present if role not in picks]
    if missing:
        return {
            "itemId": item_id,
            "title": title,
            "reason": f"no candidate photo resolved for: {', '.join(missing)}",
        }

    candidate_score = score(combine([verdicts[picks[role].image.url] for role in roles_present]))
    current_score = score(
        combine([_classify_stored(storage, current[role].storage_key) for role in roles_present])
    )
    if not should_replace(current_score, candidate_score):
        return None

    used_geometry = any(picks[role].tier == "geometry" for role in roles_present)
    tier = "geometry" if used_geometry else "metadata"
    # Only a role this record already has a stored photo for was scored above
    # and may be replaced — a role `pick_roles` opportunistically resolved
    # beyond that (say, a "reverse" candidate for a record with no reverse
    # stored at all) is not this step's job to add; that is out of scope
    # (docs/05-integrations.md, section 13).
    return ItemDiff(
        item_id=item_id,
        title=title,
        year=year,
        current_score=round(current_score, 3),
        candidate_score=round(candidate_score, 3),
        tier=tier,
        obverse_url=picks["obverse"].image.url if "obverse" in roles_present else None,
        reverse_url=picks["reverse"].image.url if "reverse" in roles_present else None,
    )


# --------------------------------------------------------------------- scan
class BoundedList(list[Any]):
    """A list capped at `limit` items; `overflow` counts what did not fit.

    Used for every "examples" collection the report shows — memory stays a
    small constant no matter how many times `add` is called over a run of
    any size, so the report itself can never be the thing that grows with
    the size of the catalogue.
    """

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self.overflow = 0

    def add(self, item: Any) -> None:
        if len(self) < self.limit:
            self.append(item)
        else:
            self.overflow += 1


@dataclass
class PhotoUpgradeOutcome:
    scanned: int = 0
    with_replacement: int = 0
    fallback_count: int = 0
    without_page: int = 0
    failed_count: int = 0
    replaced_count: int = 0
    failed_apply_count: int = 0
    duplicate_title_groups: int = 0
    diffs_sample: BoundedList = field(default_factory=lambda: BoundedList(SAMPLE_LIMIT))
    fallbacks: BoundedList = field(default_factory=lambda: BoundedList(SAMPLE_LIMIT))
    failed: BoundedList = field(default_factory=lambda: BoundedList(SAMPLE_LIMIT))
    replaced: BoundedList = field(default_factory=lambda: BoundedList(SAMPLE_LIMIT))
    duplicate_titles: BoundedList = field(default_factory=lambda: BoundedList(SAMPLE_LIMIT))

    def summary(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "withReplacement": self.with_replacement,
            "fallbacks": self.fallback_count,
            "withoutPage": self.without_page,
            "failed": self.failed_count,
            "replaced": self.replaced_count,
            "failedApply": self.failed_apply_count,
            "duplicateTitleGroups": self.duplicate_title_groups,
        }


def _diff_row(diff: ItemDiff) -> dict[str, Any]:
    return {
        "decision": "",
        "itemId": diff.item_id,
        "title": diff.title,
        "year": diff.year,
        "currentScore": diff.current_score,
        "candidateScore": diff.candidate_score,
        "tier": diff.tier,
        "obverseUrl": diff.obverse_url or "",
        "reverseUrl": diff.reverse_url or "",
        "note": diff.note,
    }


class _DiffCsvWriter:
    """One row at a time, flushed immediately — open for the whole run
    rather than built up in memory and written at the end."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("w", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._handle, fieldnames=CSV_COLUMNS)
        self._writer.writeheader()

    def write(self, diff: ItemDiff) -> None:
        self._writer.writerow(_diff_row(diff))
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def write_diff_csv(path: Path, diffs: Sequence[ItemDiff]) -> int:
    """Convenience wrapper for a caller that already has the full list of
    diffs in hand (tests; a person re-rendering a saved run) — `run()` itself
    writes through `_DiffCsvWriter` one row at a time as it scans."""
    writer = _DiffCsvWriter(path)
    try:
        for diff in diffs:
            writer.write(diff)
    finally:
        writer.close()
    return len(diffs)


def read_review_csv(path: Path) -> set[int]:
    """Item ids marked `decision=yes` in a previously written diff CSV. The
    URL columns are never read back: re-running against the same cached
    pages resolves the same candidates, so a hand edit of them would do
    nothing — only `decision` narrows which of the recomputed rows apply."""
    chosen: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() in YES:
                chosen.add(int(str(row["itemId"]).strip()))
    return chosen


async def run(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    country_id: int,
    limit: int | None,
    log: Callable[[str], None],
    diff_out: Path | None = None,
    apply: bool = False,
    only_item_ids: set[int] | None = None,
) -> PhotoUpgradeOutcome:
    """One streaming pass over the candidates: score, compare, optionally
    write a CSV row and replace, then move to the next record. Nothing about
    one record's gallery or verdicts is still reachable once its iteration
    ends — see the module docstring and `tests/test_photo_upgrade.py`'s own
    memory-boundedness test.

    `apply=False` (the default, a dry run) never calls `photo_replace`.
    `apply=True` with `only_item_ids=None` replaces every confident-win row
    this pass computes; a non-None set (from a previously saved diff CSV,
    `read_review_csv`) restricts that to the ids it names.
    """
    outcome = PhotoUpgradeOutcome()
    title_rows = await _title_year_rows(session, country_id=country_id)
    duplicates = find_duplicate_titles(title_rows)
    outcome.duplicate_title_groups = len(duplicates)
    for row in duplicates:
        outcome.duplicate_titles.add(row)

    candidates = await candidate_items(session, country_id=country_id)
    outcome.without_page = max(len(title_rows) - len(candidates), 0)
    if limit is not None:
        candidates = candidates[:limit]
    total = len(candidates)

    writer = _DiffCsvWriter(diff_out) if diff_out is not None else None
    try:
        for index, (item_id, title, year, url) in enumerate(candidates, start=1):
            outcome.scanned += 1
            status = await _process_one(
                session,
                storage=storage,
                client=client,
                item_id=item_id,
                title=title,
                year=year,
                url=url,
                outcome=outcome,
                writer=writer,
                apply=apply,
                only_item_ids=only_item_ids,
            )
            log(f"[{index}/{total}] {title} ({year}) … {status}")
    finally:
        if writer is not None:
            writer.close()
    return outcome


async def _process_one(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    item_id: int,
    title: str,
    year: int,
    url: str,
    outcome: PhotoUpgradeOutcome,
    writer: _DiffCsvWriter | None,
    apply: bool,
    only_item_ids: set[int] | None,
) -> str:
    """One record's worth of work; returns the progress-line status word."""
    try:
        result = await _diff_for_item(
            session,
            storage=storage,
            client=client,
            item_id=item_id,
            title=title,
            year=year,
            url=url,
        )
    except Exception as exc:  # a bad page or a bad object must not stop the run
        outcome.failed_count += 1
        outcome.failed.add({"itemId": item_id, "title": title, "error": str(exc)})
        return "failed"

    if result is None:
        return "kept"

    if isinstance(result, dict):
        reason = str(result["reason"])
        if reason.startswith(("page unreachable", "no gallery images")):
            outcome.failed_count += 1
            outcome.failed.add(result)
            return "no-page"
        outcome.fallback_count += 1
        outcome.fallbacks.add(result)
        return "fallback"

    outcome.with_replacement += 1
    outcome.diffs_sample.add(result)
    if writer is not None:
        writer.write(result)
    if apply and (only_item_ids is None or item_id in only_item_ids):
        try:
            applied = await photo_replace.replace_photos(
                session,
                storage=storage,
                client=client,
                item_id=item_id,
                urls={"obverse": result.obverse_url, "reverse": result.reverse_url},
                license="ua-coins.info, © 2015-2026, used with attribution",
                attribution="ua-coins.info",
            )
            await session.commit()
            outcome.replaced_count += 1
            outcome.replaced.add(applied)
        except Exception as exc:  # one bad replacement must not stop the run
            await session.rollback()
            outcome.failed_apply_count += 1
            outcome.failed.add({"itemId": item_id, "error": str(exc)})
    return "upgraded"
