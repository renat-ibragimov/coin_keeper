import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { CollectionGroup, MetalKind } from '@/shared/api/types';

export const COLLECTION_SORTS = ['date', 'title', 'total'] as const;
export type CollectionSort = (typeof COLLECTION_SORTS)[number];
export type CollectionView = 'cards' | 'table';

export interface CollectionFilters {
  q: string;
  countryId?: number;
  seriesId?: number;
  yearFrom?: number;
  yearTo?: number;
  denominationId?: number;
  group?: CollectionGroup;
  metalKind?: MetalKind;
  grade?: string;
  sort: CollectionSort;
  order: 'asc' | 'desc';
  page: number;
  view: CollectionView;
}

const GROUPS: CollectionGroup[] = ['circulation', 'commemorative', 'collector', 'other'];
const METALS: MetalKind[] = ['precious', 'base', 'unknown'];

function intParam(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key);
  if (!raw) return undefined;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** The URL is the state (same rule as the catalog): F5 and shared links restore the listing. */
export function parseCollectionFilters(params: URLSearchParams): CollectionFilters {
  const sort = params.get('sort');
  const view = params.get('view');
  const group = params.get('group');
  const metalKind = params.get('metalKind');
  const grade = params.get('grade');
  return {
    q: params.get('q') ?? '',
    countryId: intParam(params, 'countryId'),
    seriesId: intParam(params, 'seriesId'),
    yearFrom: intParam(params, 'yearFrom'),
    yearTo: intParam(params, 'yearTo'),
    denominationId: intParam(params, 'denominationId'),
    group: GROUPS.includes(group as CollectionGroup) ? (group as CollectionGroup) : undefined,
    metalKind: METALS.includes(metalKind as MetalKind) ? (metalKind as MetalKind) : undefined,
    grade: grade || undefined,
    sort: COLLECTION_SORTS.includes(sort as CollectionSort) ? (sort as CollectionSort) : 'date',
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
  setIf('q', filters.q);
  setIf('countryId', filters.countryId);
  setIf('seriesId', filters.seriesId);
  setIf('yearFrom', filters.yearFrom);
  setIf('yearTo', filters.yearTo);
  setIf('denominationId', filters.denominationId);
  setIf('group', filters.group);
  setIf('metalKind', filters.metalKind);
  setIf('grade', filters.grade);
  if (filters.sort !== 'date') params.set('sort', filters.sort);
  if (filters.order !== 'desc') params.set('order', filters.order);
  if (filters.page > 1) params.set('page', String(filters.page));
  if (filters.view !== 'cards') params.set('view', filters.view);
  return params;
}

export function hasActiveFilters(filters: CollectionFilters): boolean {
  return Boolean(
    filters.q ||
    filters.countryId ||
    filters.seriesId ||
    filters.yearFrom ||
    filters.yearTo ||
    filters.denominationId ||
    filters.group ||
    filters.metalKind ||
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
          // A new country invalidates the series chosen under the old one.
          if ('countryId' in changes && !('seriesId' in changes)) next.seriesId = undefined;
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
