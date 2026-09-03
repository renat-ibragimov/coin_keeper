"""The reconnaissance report: JSON for the record, a summary for the terminal.

Same shape of thing as the migration report: counts, tables, examples,
warnings, assumptions. It never contains anything private — the catalogue
side is the shared catalogue only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA, SOURCES
from app.ukraine_recon.triangulate import STRATEGIES

SOURCE_LABELS = {SOURCE_NBU: "nbu", SOURCE_UA_COINS: "ua-coins", SOURCE_WIKIPEDIA: "wiki"}
CANDIDATES_IN_SUMMARY = 20
UNMATCHED_IN_SUMMARY = 20


@dataclass
class ReconReport:
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    finished_at: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    catalog: dict[str, Any] = field(default_factory=dict)
    year_table: list[dict[str, Any]] = field(default_factory=list)
    series_table: dict[str, Any] = field(default_factory=dict)
    matching: dict[str, Any] = field(default_factory=dict)
    unmatched_ours: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    images: dict[str, Any] = field(default_factory=dict)
    prices: dict[str, Any] = field(default_factory=dict)
    titles: dict[str, Any] = field(default_factory=dict)
    rights: dict[str, Any] = field(default_factory=dict)
    nbu_sample: list[dict[str, Any]] = field(default_factory=list)
    ua_coins_sample: list[dict[str, Any]] = field(default_factory=list)
    http: dict[str, Any] = field(default_factory=dict)

    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "options": self.options,
            "sources": self.sources,
            "catalog": self.catalog,
            "yearTable": self.year_table,
            "seriesTable": self.series_table,
            "matching": self.matching,
            "unmatchedOurs": self.unmatched_ours,
            "candidates": self.candidates,
            "images": self.images,
            "prices": self.prices,
            "titles": self.titles,
            "rights": self.rights,
            "nbuSample": self.nbu_sample,
            "uaCoinsSample": self.ua_coins_sample,
            "http": self.http,
            "warnings": self.warnings,
            "assumptions": self.assumptions,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------- summary
    def summary_lines(self) -> list[str]:
        lines = ["", "=== ukraine reconnaissance ==="]
        lines += self._sources_lines()
        lines += self._catalog_lines()
        lines += self._year_lines()
        lines += self._series_lines()
        lines += self._matching_lines()
        lines += self._unmatched_lines()
        lines += self._candidate_lines()
        lines += self._image_lines()
        lines += self._price_lines()
        lines += self._title_lines()
        lines += self._rights_lines()
        if self.warnings:
            lines += ["", "=== warnings ==="]
            lines += [f"  - {message}" for message in self.warnings]
        return lines

    def _sources_lines(self) -> list[str]:
        lines = ["", "--- indexes ---"]
        for name in SOURCES:
            info = self.sources.get(name)
            if not info:
                lines.append(f"  {SOURCE_LABELS[name]:<10} (not fetched)")
                continue
            access = info.get("access", "live")
            counts = info.get("summary", {})
            detail = ", ".join(
                f"{key}={value}" for key, value in counts.items() if key != "priceDates"
            )
            lines.append(
                f"  {SOURCE_LABELS[name]:<10} {info.get('records', 0):>5}  [{access}]  {detail}"
            )
        return lines

    def _catalog_lines(self) -> list[str]:
        if not self.catalog:
            return ["", "--- our catalogue: skipped ---"]
        c = self.catalog
        return [
            "",
            "--- our catalogue (shared, Ukraine) ---",
            f"  items {c.get('items')}  active {c.get('active')}  series {c.get('series')}"
            f"  years {c.get('yearRange')}",
            f"  by group {c.get('byGroup')}",
            f"  title_uk {c.get('withTitleUk')}  photo {c.get('withPhoto')}"
            f"  price {c.get('withPrice')} (suspect {c.get('withSuspectPrice')})"
            f"  source_url ua-coins {c.get('withSourceUrlUaCoins')}"
            f" / ucoin {c.get('withSourceUrlUcoin')}",
        ]

    def _year_lines(self) -> list[str]:
        if not self.year_table:
            return []
        lines = ["", "--- year x source (coins only; sets and souvenir packs excluded) ---"]
        header = (
            f"  {'year':<6}{'nbu':>6}{'ua-coins':>10}{'wiki':>6}{'ours':>6}{'(comm.)':>9}  flag"
        )
        lines.append(header)
        for row in self.year_table:
            lines.append(
                f"  {row['year']:<6}{row.get(SOURCE_NBU, 0):>6}{row.get(SOURCE_UA_COINS, 0):>10}"
                f"{row.get(SOURCE_WIKIPEDIA, 0):>6}{row['ours']:>6}"
                f"{row['oursCommemorative']:>9}  {row['flag']}"
            )
            if row["flag"] == "~":
                for title in row["disputed"][:5]:
                    lines.append(f"          . {title}")
        lines.append(
            "  flag: ~ spread of 1-2 between sources, ! more;"
            " '.' lines are coins not in every source"
        )
        return lines

    def _series_lines(self) -> list[str]:
        rows = self.series_table.get("rows")
        if not rows:
            return []
        lines = ["", "--- series x source ---"]
        lines.append(f"  {'series':<48}{'ua-coins':>9}{'nbu':>6}{'ours':>6}  ours name")
        for row in rows:
            ours = row["ours"] if row["ours"] is not None else "-"
            ua = row["uaCoins"] if row["uaCoins"] is not None else "-"
            nbu = row["nbu"] if row["nbu"] is not None else "-"
            name = (row["series"] or row["uaCoinsName"] or "?")[:46]
            lines.append(f"  {name:<48}{ua!s:>9}{nbu!s:>6}{ours!s:>6}  {row['oursSeries'] or ''}")
        for label, key in (
            ("ours, unmapped", "unmappedOurs"),
            ("ua-coins, unmapped", "unmappedUaCoins"),
            ("nbu, unmapped", "unmappedNbu"),
        ):
            entries = self.series_table.get(key) or []
            if entries:
                lines.append(
                    f"  {label}: "
                    + "; ".join(f"{e['name']} ({e.get('count', e.get('total'))})" for e in entries)
                )
        return lines

    def _matching_lines(self) -> list[str]:
        counts = self.matching.get("counts")
        if not counts:
            return []
        lines = ["", "--- our items matched, by strategy (counted once per item and source) ---"]
        lines.append(
            f"  {'source':<10}"
            + "".join(f"{s:>6}" for s in STRATEGIES)
            + f"{'total':>8}{'items':>8}"
        )
        for source in SOURCES:
            per = counts.get(source, {})
            total = sum(per.values())
            items = self.matching.get("itemsMatched", {}).get(source, 0)
            lines.append(
                f"  {SOURCE_LABELS[source]:<10}"
                + "".join(f"{per.get(s, 0):>6}" for s in STRATEGIES)
                + f"{total:>8}{items:>8}"
            )
        lines.append("  D: not applicable, no source exposes catalogue numbers")
        lines.append(
            f"  conflicts: 1->N {self.matching.get('oneToMany', 0)},"
            f" N->1 {self.matching.get('manyToOne', 0)}"
            f"; matched in any source {self.matching.get('itemsMatchedAny', 0)}"
            f", in all three {self.matching.get('itemsMatchedAll', 0)}"
        )
        return lines

    def _unmatched_lines(self) -> list[str]:
        if not self.catalog:
            return []
        lines = ["", f"--- ours without a match in any source: {len(self.unmatched_ours)} ---"]
        for item in self.unmatched_ours[:UNMATCHED_IN_SUMMARY]:
            lines.append(
                f"  #{item['id']:<6} {item['year']} {item['denomination'] or '?':>7}"
                f"  {item['title']}"
            )
        if len(self.unmatched_ours) > UNMATCHED_IN_SUMMARY:
            lines.append(
                f"  ... {len(self.unmatched_ours) - UNMATCHED_IN_SUMMARY} more in the JSON"
            )
        return lines

    def _candidate_lines(self) -> list[str]:
        lines = [
            "",
            f"--- candidates to add (in 2+ sources, not in ours): {len(self.candidates)} ---",
        ]
        for c in self.candidates[:CANDIDATES_IN_SUMMARY]:
            lines.append(
                f"  {c['year']} {c['denomination'] or '?':>7}  {c['title']}"
                f"  [{', '.join(c['sources'])}]"
            )
        if len(self.candidates) > CANDIDATES_IN_SUMMARY:
            lines.append(f"  ... {len(self.candidates) - CANDIDATES_IN_SUMMARY} more in the JSON")
        return lines

    def _image_lines(self) -> list[str]:
        if not self.images:
            return []
        lines = ["", "--- images ---"]
        for source, info in self.images.items():
            lines.append(f"  {source}:")
            for variant, stats in info.get("variants", {}).items():
                lines.append(
                    f"    {variant:<14} ok {stats.get('ok', 0)}/{stats.get('checked', 0)}"
                    f"  bytes median {stats.get('bytesMedian')}  dims {stats.get('dimensions')}"
                )
            if info.get("note"):
                lines.append(f"    note: {info['note']}")
        return lines

    def _price_lines(self) -> list[str]:
        if not self.prices:
            return []
        p = self.prices
        if not p.get("compared"):
            return ["", "--- prices: nothing to compare ---"]
        return [
            "",
            f"--- prices, ua-coins / ours (n={p['compared']}) ---",
            f"  median {p['median']}  p10 {p['p10']}  p90 {p['p90']}"
            f"  min {p['min']}  max {p['max']}",
            f"  off by 3x or more: {p['offByFactorOf3']}"
            f"  off by 10x or more: {p['offByFactorOf10']}",
        ]

    def _title_lines(self) -> list[str]:
        kinds = self.titles.get("kinds")
        if not kinds:
            return []
        lines = ["", "--- titles across sources (clusters with 2+ titles) ---"]
        lines.append("  " + ", ".join(f"{k} {v}" for k, v in kinds.items()))
        for kind, examples in self.titles.get("examples", {}).items():
            for ex in examples[:3]:
                parts = [f"{SOURCE_LABELS[s]}: {ex[s]}" for s in SOURCES if ex.get(s)]
                if ex.get("ours"):
                    parts.append(f"ours: {ex['ours']}")
                lines.append(f"  [{kind}] " + " | ".join(parts))
        return lines

    def _rights_lines(self) -> list[str]:
        if not self.rights:
            return []
        lines = ["", "--- robots.txt and terms (quoted, no conclusions) ---"]
        for source, info in self.rights.items():
            lines.append(f"  {source}: robots {info.get('robots', '?')!r}")
            for quote in info.get("quotes", [])[:3]:
                lines.append(f'    "{quote}"')
        return lines
