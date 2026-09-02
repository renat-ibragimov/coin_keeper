"""Price checks applied to the legacy snapshots.

Rules come from docs/05-integrations.md, the checks applied before a write. At migration
time a failing snapshot is not dropped — the history is worth keeping — it is
flagged with is_suspect and stays out of collection value (docs/09-data-migration.md).

Two rules read differently here than they do on the live path, and the
difference is deliberate:

* The "not a year" rule also covers a plain number in 1900-2100 when no
  currency is evident. Every legacy row carries a currency_code, so that half
  can only fire when the code is missing or unknown; the half that earns its
  keep is a price equal to the issue year of its own coin.
* The "currency is determined" rule has no source text to look at here, so it
  checks the recorded currency_code against the currencies actually present.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

MIN_PRICE = Decimal("1")
MAX_PRICE = Decimal("1000000")
YEAR_LOW = 1900
YEAR_HIGH = 2100
MAX_PLAIN_DIGITS = 7
DEVIATION_FACTOR = Decimal("10")
# Below this a "median" says nothing, so the history rule stays quiet.
MIN_HISTORY_FOR_DEVIATION = 3

RULE_RANGE = "range"
RULE_LOOKS_LIKE_YEAR = "looks_like_year"
RULE_DIGIT_RUN = "digit_run"
RULE_DEVIATION = "deviation_from_history"
RULE_CURRENCY = "currency_undetermined"

ALL_RULES = (
    RULE_RANGE,
    RULE_LOOKS_LIKE_YEAR,
    RULE_DIGIT_RUN,
    RULE_DEVIATION,
    RULE_CURRENCY,
)


@dataclass(frozen=True, slots=True)
class SnapshotUnderTest:
    snapshot_id: int
    catalog_item_id: int
    price: Decimal
    currency_code: str | None
    issue_year: int | None


@dataclass(slots=True)
class PriceVerdict:
    snapshot_id: int
    rules: list[str] = field(default_factory=list)

    @property
    def is_suspect(self) -> bool:
        return bool(self.rules)


def evaluate_all(
    snapshots: Sequence[SnapshotUnderTest], known_currencies: Iterable[str]
) -> dict[int, PriceVerdict]:
    """Check every snapshot, returning a verdict per snapshot id.

    A snapshot can break several rules at once; all of them are recorded, so
    the report can say which rule caught what.
    """
    currencies = {code.upper() for code in known_currencies}
    medians = _medians_by_item(snapshots)

    verdicts: dict[int, PriceVerdict] = {}
    for snapshot in snapshots:
        verdict = PriceVerdict(snapshot_id=snapshot.snapshot_id)

        if not (MIN_PRICE <= snapshot.price <= MAX_PRICE):
            verdict.rules.append(RULE_RANGE)

        currency_known = bool(
            snapshot.currency_code and snapshot.currency_code.upper() in currencies
        )
        if not currency_known:
            verdict.rules.append(RULE_CURRENCY)

        if _looks_like_year(snapshot, currency_known=currency_known):
            verdict.rules.append(RULE_LOOKS_LIKE_YEAR)

        if _digit_run(snapshot.price) > MAX_PLAIN_DIGITS:
            verdict.rules.append(RULE_DIGIT_RUN)

        median = medians.get(snapshot.catalog_item_id)
        if median is not None and _deviates(snapshot.price, median):
            verdict.rules.append(RULE_DEVIATION)

        verdicts[snapshot.snapshot_id] = verdict
    return verdicts


def _medians_by_item(
    snapshots: Sequence[SnapshotUnderTest],
) -> Mapping[int, Decimal]:
    grouped: dict[int, list[Decimal]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.catalog_item_id, []).append(snapshot.price)
    return {
        item_id: Decimal(statistics.median(sorted(prices)))
        for item_id, prices in grouped.items()
        if len(prices) >= MIN_HISTORY_FOR_DEVIATION
    }


def _looks_like_year(snapshot: SnapshotUnderTest, *, currency_known: bool) -> bool:
    if snapshot.price != snapshot.price.to_integral_value():
        return False
    value = int(snapshot.price)
    if snapshot.issue_year is not None and value == snapshot.issue_year:
        # The strongest signal: the price is literally this coin's year.
        return True
    return not currency_known and YEAR_LOW <= value <= YEAR_HIGH


def _digit_run(price: Decimal) -> int:
    """Digits in the integer part — a long unbroken run means glued numbers."""
    return len(str(int(abs(price))))


def _deviates(price: Decimal, median: Decimal) -> bool:
    if median <= 0 or price <= 0:
        return True
    high, low = max(price, median), min(price, median)
    return high / low > DEVIATION_FACTOR
