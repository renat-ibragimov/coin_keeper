import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { CollectionGroup } from '@/shared/api/types';

export const SORT_FIELDS = [
  'title',
  'country',
  'series',
  'year',
  'denomination',
  'material',
  'owned',
  'purchase',
  'price',
] as const;
export type SortField = (typeof SORT_FIELDS)[number];

export type Scope = 'all' | 'shared' | 'own';
export type CatalogView = 'cards' | 'table';

export interface CatalogFilters {
  q: string;
  countryIds: number[];
  seriesIds: number[];
  yearFrom?: number;
  yearTo?: number;
  denominationIds: number[];
  groups: CollectionGroup[];
  materialIds: number[];
  owned?: boolean;
  scope: Scope;
  archived: boolean;
  sort: SortField;
  order: 'asc' | 'desc';
  page: number;
  view: CatalogView;
}

const GROUPS: CollectionGroup[] = ['circulation', 'commemorative', 'collector', 'other'];

function intParam(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key);
  if (!raw) return undefined;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/** Every occurrence of a repeated query key (`countryId=1&countryId=2`),
 *  parsed and de-duplicated — the same shape `?countryId=` list the backend
 *  reads (docs/03-api-contract.md, multi-select filters, 2026-09-12). */
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

/** The URL is the single source of truth: a shared link or F5 restores the
 *  exact same listing (docs/03 filters ↔ query parameters one to one). */
export function parseFilters(params: URLSearchParams): CatalogFilters {
  const scope = params.get('scope');
  const sort = params.get('sort');
  const ownedRaw = params.get('owned');
  const view = params.get('view');
  return {
    q: params.get('q') ?? '',
    countryIds: intListParam(params, 'countryId'),
    seriesIds: intListParam(params, 'seriesId'),
    yearFrom: intParam(params, 'yearFrom'),
    yearTo: intParam(params, 'yearTo'),
    denominationIds: intListParam(params, 'denominationId'),
    groups: groupListParam(params, 'group'),
    materialIds: intListParam(params, 'materialId'),
    owned: ownedRaw === 'true' ? true : ownedRaw === 'false' ? false : undefined,
    scope: scope === 'shared' || scope === 'own' ? scope : 'all',
    archived: params.get('archived') === 'true',
    sort: SORT_FIELDS.includes(sort as SortField) ? (sort as SortField) : 'title',
    order: params.get('order') === 'desc' ? 'desc' : 'asc',
    page: intParam(params, 'page') ?? 1,
    // A stale `?view=map` (the completeness map was removed) quietly degrades to cards.
    view: view === 'table' ? 'table' : 'cards',
  };
}

export function serializeFilters(filters: CatalogFilters): URLSearchParams {
  const params = new URLSearchParams();
  const setIf = (key: string, value: string | number | boolean | undefined, skip?: unknown) => {
    if (value === undefined || value === '' || value === skip) return;
    params.set(key, String(value));
  };
  const setList = (key: string, values: (number | string)[]) => {
    for (const value of values) params.append(key, String(value));
  };
  setIf('q', filters.q);
  setList('countryId', filters.countryIds);
  setList('seriesId', filters.seriesIds);
  setIf('yearFrom', filters.yearFrom);
  setIf('yearTo', filters.yearTo);
  setList('denominationId', filters.denominationIds);
  setList('group', filters.groups);
  setList('materialId', filters.materialIds);
  if (filters.owned !== undefined) params.set('owned', String(filters.owned));
  setIf('scope', filters.scope, 'all');
  if (filters.archived) params.set('archived', 'true');
  setIf('sort', filters.sort, 'title');
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
