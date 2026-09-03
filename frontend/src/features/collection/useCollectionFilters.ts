import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export const COLLECTION_SORTS = ['date', 'title', 'total'] as const;
export type CollectionSort = (typeof COLLECTION_SORTS)[number];
export type CollectionView = 'cards' | 'list';

export interface CollectionFilters {
  q: string;
  countryId?: number;
  seriesId?: number;
  sort: CollectionSort;
  order: 'asc' | 'desc';
  page: number;
  view: CollectionView;
}

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
  return {
    q: params.get('q') ?? '',
    countryId: intParam(params, 'countryId'),
    seriesId: intParam(params, 'seriesId'),
    sort: COLLECTION_SORTS.includes(sort as CollectionSort) ? (sort as CollectionSort) : 'date',
    order: params.get('order') === 'asc' ? 'asc' : 'desc',
    page: intParam(params, 'page') ?? 1,
    view: view === 'list' ? 'list' : 'cards',
  };
}

export function serializeCollectionFilters(filters: CollectionFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set('q', filters.q);
  if (filters.countryId) params.set('countryId', String(filters.countryId));
  if (filters.seriesId) params.set('seriesId', String(filters.seriesId));
  if (filters.sort !== 'date') params.set('sort', filters.sort);
  if (filters.order !== 'desc') params.set('order', filters.order);
  if (filters.page > 1) params.set('page', String(filters.page));
  if (filters.view !== 'cards') params.set('view', filters.view);
  return params;
}

export function hasActiveFilters(filters: CollectionFilters): boolean {
  return Boolean(filters.q || filters.countryId || filters.seriesId);
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
