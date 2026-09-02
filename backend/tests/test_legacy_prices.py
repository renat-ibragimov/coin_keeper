"""Price checks applied during migration (docs/05-integrations.md)."""

from __future__ import annotations

from decimal import Decimal

from app.legacy_migration.prices import (
    RULE_CURRENCY,
    RULE_DEVIATION,
    RULE_DIGIT_RUN,
    RULE_LOOKS_LIKE_YEAR,
    RULE_RANGE,
    SnapshotUnderTest,
    evaluate_all,
)

CURRENCIES = ["UAH", "USD", "EUR"]


def _snapshot(
    snapshot_id: int,
    price: str,
    *,
    item: int = 1,
    currency: str | None = "UAH",
    year: int | None = 2018,
) -> SnapshotUnderTest:
    return SnapshotUnderTest(snapshot_id, item, Decimal(price), currency, year)


def test_sane_prices_are_left_alone() -> None:
    snapshots = [
        _snapshot(1, "666.00"),
        _snapshot(2, "700.00"),
        _snapshot(3, "650.00"),
    ]
    verdicts = evaluate_all(snapshots, CURRENCIES)
    assert all(not v.is_suspect for v in verdicts.values())


def test_zero_and_negative_fail_the_range_rule() -> None:
    verdicts = evaluate_all([_snapshot(1, "0.00"), _snapshot(2, "-5.00")], CURRENCIES)
    assert RULE_RANGE in verdicts[1].rules
    assert RULE_RANGE in verdicts[2].rules


def test_price_above_a_million_fails_the_range_rule() -> None:
    verdicts = evaluate_all([_snapshot(1, "1000001.00")], CURRENCIES)
    assert RULE_RANGE in verdicts[1].rules


def test_price_equal_to_the_issue_year_is_suspect() -> None:
    """The legacy parser sometimes captured the year instead of the price."""
    verdicts = evaluate_all([_snapshot(1, "2018.00", year=2018)], CURRENCIES)
    assert RULE_LOOKS_LIKE_YEAR in verdicts[1].rules


def test_plain_year_without_a_known_currency_is_suspect() -> None:
    verdicts = evaluate_all([_snapshot(1, "1999.00", currency="XYZ", year=2018)], CURRENCIES)
    assert RULE_LOOKS_LIKE_YEAR in verdicts[1].rules
    assert RULE_CURRENCY in verdicts[1].rules


def test_a_long_digit_run_is_flagged_as_glue() -> None:
    """12001500 instead of 1200: sanitize-ucoin-glued-prices in the legacy log."""
    verdicts = evaluate_all([_snapshot(1, "12001500.00")], CURRENCIES)
    assert RULE_DIGIT_RUN in verdicts[1].rules


def test_deviation_from_the_median_is_flagged() -> None:
    snapshots = [
        _snapshot(1, "600.00"),
        _snapshot(2, "650.00"),
        _snapshot(3, "700.00"),
        _snapshot(4, "90000.00"),
    ]
    verdicts = evaluate_all(snapshots, CURRENCIES)
    assert RULE_DEVIATION in verdicts[4].rules
    assert not verdicts[2].is_suspect


def test_deviation_stays_quiet_without_enough_history() -> None:
    """Two points do not make a median worth trusting."""
    snapshots = [_snapshot(1, "600.00"), _snapshot(2, "90000.00")]
    verdicts = evaluate_all(snapshots, CURRENCIES)
    assert RULE_DEVIATION not in verdicts[2].rules


def test_unknown_currency_is_flagged() -> None:
    verdicts = evaluate_all([_snapshot(1, "30.00", currency="XYZ")], CURRENCIES)
    assert RULE_CURRENCY in verdicts[1].rules


def test_all_broken_rules_are_recorded_not_just_the_first() -> None:
    """The report says which rule caught what, so every hit is kept."""
    snapshots = [
        _snapshot(1, "600.00"),
        _snapshot(2, "650.00"),
        _snapshot(3, "700.00"),
        _snapshot(4, "12001500.00"),
    ]
    verdicts = evaluate_all(snapshots, CURRENCIES)
    assert set(verdicts[4].rules) == {RULE_RANGE, RULE_DIGIT_RUN, RULE_DEVIATION}
