import type { CompletenessGroup } from '@/shared/api/types';

export type CompletenessSort = 'completion' | 'value';

function label(row: CompletenessGroup): string {
  return row.label ?? '';
}

/** Most complete first (ties: larger group, then label) -- or by the
 *  dimension's own natural order when it has one (a year, a denomination's
 *  face value), falling back to the label otherwise (a series, a material). */
export function sortGroups(rows: CompletenessGroup[], sort: CompletenessSort): CompletenessGroup[] {
  const copy = [...rows];
  if (sort === 'value') {
    return copy.sort((a, b) => {
      if (a.sortOrder != null && b.sortOrder != null) return a.sortOrder - b.sortOrder;
      return label(a).localeCompare(label(b));
    });
  }
  return copy.sort(
    (a, b) =>
      b.summary.completionPercent - a.summary.completionPercent ||
      b.summary.total - a.summary.total ||
      label(a).localeCompare(label(b)),
  );
}
