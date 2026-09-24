import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { CollectionGroup, MetalKind } from '@/shared/api/types';
import type { PeriodFilterValue } from '@/shared/lib/periodFilter';
import { hasPeriodValue, parsePeriod, serializePeriod } from '@/shared/lib/periodFilter';

// Every column of the table sorts, and the toolbar offers the same list
// (docs/ui.md); the order here is the order of the columns.
export const COLLECTION_SORTS = [
  'release',
  'title',
  'country',
  'series',
  'quantity',
  'total',
  'valuation',
  'date',
  'grade',
] as const;
export type CollectionSort = (typeof COLLECTION_SORTS)[number];
export type CollectionView = 'cards' | 'table';

export interface CollectionFilters {
  q: string;
  countryIds: number[];
  seriesIds: number[];
  period: PeriodFilterValue;
  denominationIds: number[];
  groups: CollectionGroup[];
  materialIds: number[];
  metalKinds: MetalKind[];
  grade?: string;
  sort: CollectionSort;
  order: 'asc' | 'desc';
  page: number;
  view: CollectionView;
}

const GROUPS: CollectionGroup[] = ['circulation', 'commemorative', 'collector', 'other'];
const METAL_KINDS: MetalKind[] = ['precious', 'base'];

function intParam(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key);
  if (!raw) return undefined;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** Every occurrence of a repeated query key (`countryId=1&countryId=2`),
 *  parsed and de-duplicated — the same shape the catalog's own multi-select
 *  filters use (docs/api.md, "Multi-value filters"). */
function intListParam(params: URLSearchParams, key: string): number[] {
  const seen = new Set<number>();
  for (const raw of params.getAll(key)) {
    const value = Number.parseInt(raw, 10);
    if (Number.isFinite(value) && value > 0) seen.add(value);
  }
  return [...seen];
}

function groupListParam(params: URLSearchParams, key: string): CollectionGroup[] {
  const seen = new Set<CollectionGroup>();
  for (const raw of params.getAll(key)) {
    if (GROUPS.includes(raw as CollectionGroup)) seen.add(raw as CollectionGroup);
  }
  return [...seen];
}

function metalKindListParam(params: URLSearchParams): MetalKind[] {
  return params
    .getAll('metalKind')
    .filter((value): value is MetalKind => METAL_KINDS.includes(value as MetalKind));
}

/** The URL is the state (same rule as the catalog): F5 and shared links restore the listing. */
export function parseCollectionFilters(params: URLSearchParams): CollectionFilters {
  const sort = params.get('sort');
  const view = params.get('view');
  const grade = params.get('grade');
  return {
    q: params.get('q') ?? '',
    countryIds: intListParam(params, 'countryId'),
    seriesIds: intListParam(params, 'seriesId'),
    period: parsePeriod(params),
    denominationIds: intListParam(params, 'denominationId'),
    groups: groupListParam(params, 'group'),
    materialIds: intListParam(params, 'materialId'),
    metalKinds: metalKindListParam(params),
    grade: grade || undefined,
    sort: COLLECTION_SORTS.includes(sort as CollectionSort) ? (sort as CollectionSort) : 'release',
    order: params.get('order') === 'asc' ? 'asc' : 'desc',
    page: intParam(params, 'page') ?? 1,
    view: view === 'table' ? 'table' : 'cards',
  };
}

export function serializeCollectionFilters(filters: CollectionFilters): URLSearchParams {
  const params = new URLSearchParams();
  const setIf = (key: string, value: string | number | undefined) => {
    if (value === undefined || value === '') return;
    params.set(key, String(value));
  };
  const setList = (key: string, values: (number | string)[]) => {
    for (const value of values) params.append(key, String(value));
  };
  setIf('q', filters.q);
  setList('countryId', filters.countryIds);
  setList('seriesId', filters.seriesIds);
  serializePeriod(params, filters.period);
  setList('denominationId', filters.denominationIds);
  setList('group', filters.groups);
  setList('materialId', filters.materialIds);
  setList('metalKind', filters.metalKinds);
  setIf('grade', filters.grade);
  if (filters.sort !== 'release') params.set('sort', filters.sort);
  if (filters.order !== 'desc') params.set('order', filters.order);
  if (filters.page > 1) params.set('page', String(filters.page));
  if (filters.view !== 'cards') params.set('view', filters.view);
  return params;
}

export function hasActiveFilters(filters: CollectionFilters): boolean {
  return Boolean(
    filters.q ||
    filters.countryIds.length > 0 ||
    filters.seriesIds.length > 0 ||
    hasPeriodValue(filters.period) ||
    filters.denominationIds.length > 0 ||
    filters.groups.length > 0 ||
    filters.materialIds.length > 0 ||
    filters.metalKinds.length > 0 ||
    filters.grade,
  );
}

export function useCollectionFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseCollectionFilters(searchParams), [searchParams]);

  const update = useCallback(
    (changes: Partial<CollectionFilters>) => {
      setSearchParams(
        (current) => {
          const next = { ...parseCollectionFilters(current), ...changes };
          // A changed country selection invalidates the series chosen under the old one.
          if ('countryIds' in changes && !('seriesIds' in changes)) next.seriesIds = [];
          if (!('page' in changes)) next.page = 1;
          return serializeCollectionFilters(next);
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const reset = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true });
  }, [setSearchParams]);

  return { filters, update, reset };
}
