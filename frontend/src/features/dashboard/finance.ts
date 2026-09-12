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
 * Every series the viewer has started (at least one coin owned), by how
 * filled it is — least complete first, a finished series (ratio 1) last
 * since it is the highest possible value. Equal fill breaks alphabetically.
 * A series with no coins owned at all is left out entirely.
 */
export function myCollectionSeries(entries: SeriesBreakdownEntry[]): SeriesProgress[] {
  return entries
    .filter((entry) => entry.count > 0 && entry.owned > 0)
    .map((entry) => ({
      ...entry,
      ratio: entry.owned / entry.count,
      missing: entry.count - entry.owned,
    }))
    .sort((a, b) => a.ratio - b.ratio || a.name.localeCompare(b.name));
}
