import type { SeriesBreakdownEntry } from '@/shared/api/types';

export interface ValueDelta {
  /** market value − total spend, in hryvnia */
  diffUah: number;
  /** the same as a share of the spend; null when nothing was spent */
  percent: number | null;
}

/**
 * "Різниця" on the overview: how the current valuation compares with what
 * was spent on the hobby. Display-only arithmetic over API strings — the
 * server keeps the exact sums, this only feeds a formatted label.
 */
export function valueDelta(totalSpendUah: string, marketValueUah: string): ValueDelta {
  const spend = Number(totalSpendUah);
  const value = Number(marketValueUah);
  if (!Number.isFinite(spend) || !Number.isFinite(value)) return { diffUah: 0, percent: null };
  const diffUah = Math.round((value - spend) * 100) / 100;
  const percent = spend > 0 ? (diffUah / spend) * 100 : null;
  return { diffUah, percent };
}

export interface SeriesProgress extends SeriesBreakdownEntry {
  /** 0..1 */
  ratio: number;
  missing: number;
}

/**
 * Series still in progress, the most complete first. Completed series and
 * empty ones (no items at all) are left out — there is nothing to finish.
 */
export function nearestToCompletion(entries: SeriesBreakdownEntry[]): SeriesProgress[] {
  return entries
    .filter((entry) => entry.count > 0 && entry.owned < entry.count)
    .map((entry) => ({
      ...entry,
      ratio: entry.owned / entry.count,
      missing: entry.count - entry.owned,
    }))
    .sort((a, b) => b.ratio - a.ratio || a.missing - b.missing || a.name.localeCompare(b.name));
}
