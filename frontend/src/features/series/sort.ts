import type { SeriesProgress } from '@/shared/api/types';

export type SeriesSort = 'completion' | 'name';

/** Most complete first (ties: larger series), or alphabetically. */
export function sortSeries(rows: SeriesProgress[], sort: SeriesSort): SeriesProgress[] {
  const copy = [...rows];
  if (sort === 'name') {
    return copy.sort((a, b) => a.series.name.localeCompare(b.series.name));
  }
  return copy.sort(
    (a, b) =>
      b.summary.completionPercent - a.summary.completionPercent ||
      b.summary.total - a.summary.total ||
      a.series.name.localeCompare(b.series.name),
  );
}
