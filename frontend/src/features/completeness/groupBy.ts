import type { TFunction } from 'i18next';

import type { CompletenessGroup } from '@/shared/api/types';

export type CompletenessGroupBy = 'series' | 'year' | 'denomination' | 'material';

const GROUP_BY_VALUES: CompletenessGroupBy[] = ['series', 'year', 'denomination', 'material'];

function isGroupBy(value: string | null | undefined): value is CompletenessGroupBy {
  return GROUP_BY_VALUES.includes(value as CompletenessGroupBy);
}

/** Falls back to `'series'` -- the tab's original, and still most common, view. */
export function parseGroupBy(value: string | null | undefined): CompletenessGroupBy {
  return isGroupBy(value) ? value : 'series';
}

const GROUP_BY_LABEL_KEYS: Record<CompletenessGroupBy, string> = {
  series: 'completeness.groupBySeries',
  year: 'completeness.groupByYear',
  denomination: 'completeness.groupByDenomination',
  material: 'completeness.groupByMaterial',
};

export function groupByOptions(t: TFunction): { value: CompletenessGroupBy; label: string }[] {
  return GROUP_BY_VALUES.map((value) => ({ value, label: t(GROUP_BY_LABEL_KEYS[value]) }));
}

const UNASSIGNED_LABEL_KEYS: Record<CompletenessGroupBy, string> = {
  series: 'completeness.unassignedSeries',
  year: 'completeness.unassignedYear',
  denomination: 'completeness.unassignedDenomination',
  material: 'completeness.unassignedMaterial',
};

/** `row.label` for a real group value, or the "без значення" copy for the
 *  bucket of items that carry no value on this dimension at all. */
export function groupLabel(t: TFunction, groupBy: CompletenessGroupBy, row: CompletenessGroup) {
  return row.unassigned ? t(UNASSIGNED_LABEL_KEYS[groupBy]) : (row.label ?? '');
}

/** The detail route's `:value` segment -- `'none'` for the unassigned bucket,
 *  the numeric id/year otherwise. */
export function groupRouteValue(row: { unassigned: boolean; value: number | null }): string {
  return row.unassigned || row.value === null ? 'none' : String(row.value);
}
