import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { CollectionGroup, MetalKind } from '@/shared/api/types';

export const SORT_FIELDS = [
  'country',
  'title',
  'series',
  'year',
  'denomination',
  'owned',
  'purchase',
  'price',
] as const;
export type SortField = (typeof SORT_FIELDS)[number];

export type Scope = 'all' | 'shared' | 'own';
export type CatalogView = 'cards' | 'table' | 'map';

export interface CatalogFilters {
  q: string;
  countryId?: number;
  seriesId?: number;
  yearFrom?: number;
  yearTo?: number;
  denominationId?: number;
  group?: CollectionGroup;
  metalKind?: MetalKind;
  owned?: boolean;
  scope: Scope;
  archived: boolean;
  sort: SortField;
  order: 'asc' | 'desc';
  page: number;
  view: CatalogView;
}

const GROUPS: CollectionGroup[] = ['circulation', 'commemorative', 'collector', 'other'];
const METALS: MetalKind[] = ['precious', 'base', 'unknown'];

function intParam(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key);
  if (!raw) return undefined;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** The URL is the single source of truth: a shared link or F5 restores the
 *  exact same listing (docs/03 filters ↔ query parameters one to one). */
export function parseFilters(params: URLSearchParams): CatalogFilters {
  const group = params.get('group');
  const metalKind = params.get('metalKind');
  const scope = params.get('scope');
  const sort = params.get('sort');
  const ownedRaw = params.get('owned');
  const view = params.get('view');
  return {
    q: params.get('q') ?? '',
    countryId: intParam(params, 'countryId'),
    seriesId: intParam(params, 'seriesId'),
    yearFrom: intParam(params, 'yearFrom'),
    yearTo: intParam(params, 'yearTo'),
    denominationId: intParam(params, 'denominationId'),
    group: GROUPS.includes(group as CollectionGroup) ? (group as CollectionGroup) : undefined,
    metalKind: METALS.includes(metalKind as MetalKind) ? (metalKind as MetalKind) : undefined,
    owned: ownedRaw === 'true' ? true : ownedRaw === 'false' ? false : undefined,
    scope: scope === 'shared' || scope === 'own' ? scope : 'all',
    archived: params.get('archived') === 'true',
    sort: SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : 'country',
    order: params.get('order') === 'desc' ? 'desc' : 'asc',
    page: intParam(params, 'page') ?? 1,
    view: view === 'table' || view === 'map' ? view : 'cards',
  };
}

export function serializeFilters(filters: CatalogFilters): URLSearchParams {
  const params = new URLSearchParams();
  const setIf = (key: string, value: string | number | boolean | undefined, skip?: unknown) => {
    if (value === undefined || value === '' || value === skip) return;
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
  if (filters.owned !== undefined) params.set('owned', String(filters.owned));
  setIf('scope', filters.scope, 'all');
  if (filters.archived) params.set('archived', 'true');
  setIf('sort', filters.sort, 'country');
  setIf('order', filters.order, 'asc');
  setIf('page', filters.page, 1);
  setIf('view', filters.view, 'cards');
  return params;
}

export function useCatalogFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);

  const update = useCallback(
    (changes: Partial<CatalogFilters>) => {
      setSearchParams(
        (current) => {
          const next = { ...parseFilters(current), ...changes };
          // Any change except paging itself starts from the first page.
          if (!('page' in changes)) next.page = 1;
          return serializeFilters(next);
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
