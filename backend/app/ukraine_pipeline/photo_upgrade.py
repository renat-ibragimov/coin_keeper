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


# --------------------------------------------------------------------- scan
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


@dataclass
class PhotoUpgradeOutcome:
    diffs: list[ItemDiff] = field(default_factory=list)
    scanned: int = 0
    without_page: int = 0
    fallbacks: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    duplicate_titles: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "withReplacement": len(self.diffs),
            "fallbacks": len(self.fallbacks),
            "withoutPage": self.without_page,
            "failed": len(self.failed),
            "duplicateTitles": len(self.duplicate_titles),
        }


async def candidate_items(
    session: AsyncSession, *, country_id: int
) -> list[tuple[CatalogItem, str]]:
    """(record, ua-coins.info page URL) for every shared, active Ukrainian
    record a link already names an absolute URL for. Bare legacy ids (no
    slug, no URL) cannot be turned into a fetchable page without guessing at
    one, so they fall out of this — into `without_page`, not treated as a
    page we know."""
    rows = await session.execute(
        select(CatalogItem, PriceSourceLink.external_id)
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
    return [(item, url) for item, url in rows.all()]


async def _active_items(session: AsyncSession, *, country_id: int) -> list[CatalogItem]:
    rows = await session.execute(
        select(CatalogItem).where(
            CatalogItem.country_id == country_id,
            CatalogItem.created_by.is_(None),
            CatalogItem.is_archived.is_(False),
        )
    )
    return list(rows.scalars().all())


def find_duplicate_titles(items: Sequence[CatalogItem]) -> list[dict[str, Any]]:
    """{title_original, issue_year} shared by 2+ active records — a report-only
    addendum (docs/BACKLOG.md decides what, if anything, to do about it)."""
    groups: dict[tuple[str, int], list[int]] = {}
    for item in items:
        groups.setdefault((item.title_original, item.issue_year), []).append(item.id)
    return [
        {"titleOriginal": title, "issueYear": year, "itemIds": sorted(ids)}
        for (title, year), ids in sorted(groups.items())
        if len(ids) >= 2
    ]


def _suffix_of(url: str) -> str:
    return Path(url.split("?", 1)[0]).suffix or ".img"


def _classify_url(client: PoliteClient, url: str) -> Verdict | None:
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
    item: CatalogItem,
    url: str,
) -> ItemDiff | dict[str, Any] | None:
    current = await photo_replace.official_photos(session, item.id)
    roles_present = [role for role in ROLES if role in current]
    if not roles_present:
        return None  # nothing stored yet for this record — out of scope here

    page = client.get(url)
    if not page.ok:
        return {
            "itemId": item.id,
            "title": item.title_original,
            "reason": f"page unreachable: HTTP {page.status}",
        }
    images = ua_coins.parse_coin_gallery(page.text)
    if not images:
        return {
            "itemId": item.id,
            "title": item.title_original,
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
            "itemId": item.id,
            "title": item.title_original,
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
        item_id=item.id,
        title=item.title_original,
        year=item.issue_year,
        current_score=round(current_score, 3),
        candidate_score=round(candidate_score, 3),
        tier=tier,
        obverse_url=picks["obverse"].image.url if "obverse" in roles_present else None,
        reverse_url=picks["reverse"].image.url if "reverse" in roles_present else None,
    )


async def scan(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    country_id: int,
    limit: int | None,
    log: Callable[[str], None],
) -> PhotoUpgradeOutcome:
    outcome = PhotoUpgradeOutcome()
    rows = await candidate_items(session, country_id=country_id)
    all_active = await _active_items(session, country_id=country_id)
    outcome.duplicate_titles = find_duplicate_titles(all_active)
    outcome.without_page = max(len(all_active) - len(rows), 0)

    if limit is not None:
        rows = rows[:limit]
    for index, (item, url) in enumerate(rows, start=1):
        outcome.scanned += 1
        try:
            diff = await _diff_for_item(session, storage=storage, client=client, item=item, url=url)
        except Exception as exc:  # a bad page or a bad object must not stop the run
            outcome.failed.append(
                {"itemId": item.id, "title": item.title_original, "error": str(exc)}
            )
            continue
        if isinstance(diff, ItemDiff):
            outcome.diffs.append(diff)
        elif diff is not None:
            outcome.fallbacks.append(diff)
        if index % 25 == 0 or index == len(rows):
            log(f"photo-upgrade scan {index}/{len(rows)}")
    return outcome


# -------------------------------------------------------------------- apply
@dataclass
class ApplyOutcome:
    replaced: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {"replaced": len(self.replaced), "failedApply": len(self.failed)}


async def apply_diffs(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    diffs: list[ItemDiff],
    only_item_ids: set[int] | None,
    log: Callable[[str], None],
) -> ApplyOutcome:
    """Store the candidate pair for every diff (or, with `only_item_ids`,
    only the ones a person marked `decision=yes` in the diff CSV — the URLs
    themselves are not read back from that file: re-running the same scan
    against the same cached pages resolves the same candidates, so there is
    nothing for a hand edit of the URL columns to change)."""
    outcome = ApplyOutcome()
    chosen = [d for d in diffs if only_item_ids is None or d.item_id in only_item_ids]
    for index, diff in enumerate(chosen, start=1):
        try:
            result = await photo_replace.replace_photos(
                session,
                storage=storage,
                client=client,
                item_id=diff.item_id,
                urls={"obverse": diff.obverse_url, "reverse": diff.reverse_url},
                license="ua-coins.info, © 2015-2026, used with attribution",
                attribution="ua-coins.info",
            )
            outcome.replaced.append(result)
            await session.commit()
        except Exception as exc:  # one bad replacement must not stop the run
            await session.rollback()
            outcome.failed.append({"itemId": diff.item_id, "error": str(exc)})
        log(f"photo-upgrade apply {index}/{len(chosen)}")
    return outcome


# ------------------------------------------------------------------- review
def write_diff_csv(path: Path, outcome: PhotoUpgradeOutcome) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for diff in outcome.diffs:
            writer.writerow(
                {
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
            )
    return len(outcome.diffs)


def read_review_csv(path: Path) -> set[int]:
    """Item ids marked `decision=yes` — see `apply_diffs`'s own docstring for
    why the URL columns are not read back."""
    chosen: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() in YES:
                chosen.add(int(str(row["itemId"]).strip()))
    return chosen
