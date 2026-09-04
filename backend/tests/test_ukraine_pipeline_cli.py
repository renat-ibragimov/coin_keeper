"""Command line of scripts/ukraine_pipeline.py: defaults, steps, usage errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ukraine_pipeline import report
from app.ukraine_pipeline.runner import STEPS, PipelineError, parse_steps
from scripts import ukraine_pipeline


def test_nothing_is_written_unless_asked() -> None:
    args = ukraine_pipeline._parse_args([])
    assert args.apply is False
    assert args.ua_coins == "auto"
    assert args.pause == 0.45


def test_contradicting_flags_are_a_usage_error() -> None:
    assert ukraine_pipeline.main(["--apply", "--dry-run"]) == ukraine_pipeline.EXIT_USAGE


def test_a_missing_review_file_is_a_usage_error(tmp_path: Path) -> None:
    code = ukraine_pipeline.main(["--apply-review", str(tmp_path / "nope.csv")])
    assert code == ukraine_pipeline.EXIT_USAGE


def test_steps_default_to_all_of_them_in_order() -> None:
    assert parse_steps(None) == STEPS
    # series before gaps: gaps creates records under the NBU series names.
    assert STEPS.index("series") < STEPS.index("gaps")
    # repair-gaps and merge clean up after gaps, so they run after it.
    assert STEPS.index("gaps") < STEPS.index("repair-gaps") < STEPS.index("merge")
    assert parse_steps("photos,prices") == ("photos", "prices")
    assert parse_steps("repair-gaps,merge") == ("repair-gaps", "merge")


def test_a_missing_merge_file_is_a_usage_error(tmp_path: Path) -> None:
    code = ukraine_pipeline.main(["--apply-merge", str(tmp_path / "nope.csv")])
    assert code == ukraine_pipeline.EXIT_USAGE


def test_the_report_prints_every_step() -> None:
    """A step the report does not know about runs and is never seen."""
    assert report.STEP_ORDER == STEPS


def test_an_unknown_step_stops_the_run() -> None:
    with pytest.raises(PipelineError, match="unknown steps"):
        parse_steps("bridge,teleport")
