"""Migration report.

Never contains the owner's email or password — only the user id
(docs/09-data-migration.md).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.json_support import json_default

MAX_EXAMPLES_PER_RULE = 5


@dataclass
class MigrationReport:
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    finished_at: str | None = None
    dry_run: bool = False
    skip_media: bool = False
    owner_user_id: int | None = None

    source_counts: dict[str, int] = field(default_factory=dict)
    migrated: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    suspect_by_rule: dict[str, int] = field(default_factory=dict)
    suspect_examples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    suspect_total: int = 0

    media_external: int = 0
    media_stored: int = 0
    media_missing_file: list[str] = field(default_factory=list)
    media_rejected: list[dict[str, str]] = field(default_factory=list)
    media_by_source: dict[str, int] = field(default_factory=dict)

    invalid_json_payloads: list[int] = field(default_factory=list)
    conversion_warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    checks: list[dict[str, Any]] = field(default_factory=list)
    checks_passed: bool = True

    def note_suspect(self, rule: str, example: dict[str, Any]) -> None:
        self.suspect_by_rule[rule] = self.suspect_by_rule.get(rule, 0) + 1
        examples = self.suspect_examples.setdefault(rule, [])
        if len(examples) < MAX_EXAMPLES_PER_RULE:
            examples.append(example)

    def add_check(self, name: str, expected: Any, actual: Any) -> bool:
        passed = bool(expected == actual)
        self.checks.append({"name": name, "expected": expected, "actual": actual, "passed": passed})
        if not passed:
            self.checks_passed = False
        return passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "dryRun": self.dry_run,
            "skipMedia": self.skip_media,
            "ownerUserId": self.owner_user_id,
            "sourceCounts": self.source_counts,
            "migrated": self.migrated,
            "skipped": self.skipped,
            "prices": {
                "suspectTotal": self.suspect_total,
                "byRule": self.suspect_by_rule,
                "examples": self.suspect_examples,
            },
            "media": {
                "external": self.media_external,
                "stored": self.media_stored,
                "missingFiles": self.media_missing_file,
                "rejected": self.media_rejected,
                "bySource": self.media_by_source,
            },
            "invalidJsonPayloads": self.invalid_json_payloads,
            "conversionWarnings": self.conversion_warnings,
            "assumptions": self.assumptions,
            "checks": self.checks,
            "checksPassed": self.checks_passed,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=json_default),
            encoding="utf-8",
        )

    def summary_lines(self) -> list[str]:
        lines = ["", "=== migration report ==="]
        for table, count in self.migrated.items():
            source = self.source_counts.get(table)
            suffix = f" (source: {source})" if source is not None else ""
            lines.append(f"  {table:<26} {count}{suffix}")
        if self.skipped:
            lines.append("  skipped:")
            for reason, count in self.skipped.items():
                lines.append(f"    {reason:<24} {count}")
        lines.append(f"  suspect price snapshots    {self.suspect_total}")
        for rule, count in sorted(self.suspect_by_rule.items()):
            lines.append(f"    {rule:<24} {count}")
        lines.append(f"  media external/stored      {self.media_external}/{self.media_stored}")
        if self.media_missing_file:
            lines.append(f"  media files not found      {len(self.media_missing_file)}")
        lines.append("")
        lines.append("=== checks ===")
        for check in self.checks:
            mark = "ok  " if check["passed"] else "FAIL"
            lines.append(
                f"  [{mark}] {check['name']}: expected {check['expected']!r}, "
                f"got {check['actual']!r}"
            )
        return lines
