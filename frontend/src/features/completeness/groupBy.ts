import type { TFunction } from 'i18next';

import type { CompletenessGroup } from '@/shared/api/types';

export type CompletenessGroupBy =
  'series' | 'year' | 'denomination' | 'material' | 'edge' | 'quality';

const GROUP_BY_VALUES: CompletenessGroupBy[] = [
  'series',
  'year',
  'denomination',
  'material',
  'edge',
  'quality',
];

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
  edge: 'completeness.groupByEdge',
  quality: 'completeness.groupByQuality',
};

export function groupByOptions(t: TFunction): { value: CompletenessGroupBy; label: string }[] {
  return GROUP_BY_VALUES.map((value) => ({ value, label: t(GROUP_BY_LABEL_KEYS[value]) }));
}

// "metal" has no bucket of its own -- metal_kind is NOT NULL (default
// "unknown" is itself a real, chosen group, not an absence of one).
const UNASSIGNED_LABEL_KEYS: Partial<Record<CompletenessGroupBy, string>> = {
  series: 'completeness.unassignedSeries',
  year: 'completeness.unassignedYear',
  denomination: 'completeness.unassignedDenomination',
  material: 'completeness.unassignedMaterial',
  edge: 'completeness.unassignedEdge',
  quality: 'completeness.unassignedQuality',
};

/** `row.label` for a real group value, or the "без значення" copy for the
 *  bucket of items that carry no value on this dimension at all. */
export function groupLabel(t: TFunction, groupBy: CompletenessGroupBy, row: CompletenessGroup) {
  if (row.unassigned) {
    const key = UNASSIGNED_LABEL_KEYS[groupBy];
    return key ? t(key) : '';
  }
  return row.label ?? '';
}

/** The detail route's `:value` segment -- `'none'` for the unassigned bucket,
 *  the numeric id/year or MetalKind code otherwise. */
export function groupRouteValue(row: {
  unassigned: boolean;
  value: number | string | null;
}): string {
  return row.unassigned || row.value === null ? 'none' : String(row.value);
}
