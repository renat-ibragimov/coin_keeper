"""The pipeline report: JSON for the record, a summary for the terminal.

The same shape of thing as the migration and reconnaissance reports. A step
that changed the database says what it changed and how much of it it could not
decide; a dry run says exactly what it would have done.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.json_support import json_default

STEP_ORDER = (
    "bridge",
    "series",
    "gaps",
    "repair-gaps",
    "merge",
    "titles",
    "photos",
    "prices",
    "circ-bridge",
    "circ-gaps",
    "circ-titles",
    "circ-mintage",
    "circ-photos",
)
EXAMPLES_IN_SUMMARY = 10


@dataclass
class PipelineReport:
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    finished_at: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)
    catalog: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    http: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def step(self, name: str, summary: dict[str, Any], **detail: Any) -> None:
        self.steps[name] = summary
        if detail:
            self.details[name] = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "options": self.options,
            "sources": self.sources,
            "catalog": self.catalog,
            "steps": self.steps,
            "details": self.details,
            "http": self.http,
            "warnings": self.warnings,
            "assumptions": self.assumptions,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=json_default),
            encoding="utf-8",
        )

    # --------------------------------------------------------------- summary
    def summary_lines(self) -> list[str]:
        lines = ["", "=== ukraine pipeline ==="]
        if self.options.get("dryRun"):
            lines.append("  DRY RUN — nothing was written")
        lines += self._sources_lines()
        lines += self._catalog_lines()
        for name in STEP_ORDER:
            lines += self._step_lines(name)
        if self.warnings:
            lines += ["", "=== warnings ==="]
            lines += [f"  - {message}" for message in self.warnings]
        return lines

    def _sources_lines(self) -> list[str]:
        if not self.sources:
            return []
        lines = ["", "--- sources ---"]
        for name, info in self.sources.items():
            lines.append(f"  {name:<10} {info.get('records', 0):>5}  [{info.get('access', '?')}]")
        return lines

    def _catalog_lines(self) -> list[str]:
        if not self.catalog:
            return []
        c = self.catalog
        return [
            "",
            "--- our catalogue (shared, Ukraine) ---",
            f"  items {c.get('items')}  commemorative {c.get('commemorative')}"
            f"  circulation {c.get('circulation')}  archived {c.get('archived')}",
        ]

    def _step_lines(self, name: str) -> list[str]:
        summary = self.steps.get(name)
        if summary is None:
            return []
        lines = ["", f"--- {name} ---"]
        for key, value in summary.items():
            if isinstance(value, dict):
                inner = ", ".join(f"{k}={v}" for k, v in value.items())
                lines.append(f"  {key}: {inner or '—'}")
            elif isinstance(value, list):
                lines.append(f"  {key}: {', '.join(str(v) for v in value[:EXAMPLES_IN_SUMMARY])}")
            else:
                lines.append(f"  {key}: {value}")
        return lines
