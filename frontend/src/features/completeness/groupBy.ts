import type { TFunction } from 'i18next';

import type { CompletenessGroup } from '@/shared/api/types';

export type CompletenessGroupBy =
  'series' | 'year' | 'denomination' | 'material' | 'edge' | 'quality' | 'metal';

const GROUP_BY_VALUES: CompletenessGroupBy[] = [
  'series',
  'year',
  'denomination',
  'material',
  'edge',
  'quality',
  'metal',
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
  metal: 'completeness.groupByMetal',
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

// The backend deliberately never localizes a MetalKind code (it isn't a
// dictionary row), so `row.label` is always null for this dimension -- the
// frontend renders it from `row.value` instead, reusing the same copy the
// catalog's own metal-kind filter already uses (FiltersPanel.tsx).
const METAL_LABEL_KEYS: Record<string, string> = {
  precious: 'catalog.metalPrecious',
  base: 'catalog.metalBase',
  unknown: 'catalog.metalUnknown',
};

/** `row.label` for a real group value, or the "без значення" copy for the
 *  bucket of items that carry no value on this dimension at all. */
export function groupLabel(t: TFunction, groupBy: CompletenessGroupBy, row: CompletenessGroup) {
  if (groupBy === 'metal') return t(METAL_LABEL_KEYS[String(row.value)] ?? 'catalog.metalUnknown');
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
