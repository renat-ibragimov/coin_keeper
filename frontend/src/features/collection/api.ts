import { api, toQuery } from '@/shared/api/client';
import type {
  CollectionItem,
  CollectionItemCreate,
  CollectionItemUpdate,
  CollectionPage,
} from '@/shared/api/types';

import type { CollectionFilters } from './useCollectionFilters';

export const PAGE_SIZE = 24;

export function fetchCollection(filters: CollectionFilters): Promise<CollectionPage> {
  const query = toQuery({
    page: filters.page,
    pageSize: PAGE_SIZE,
    q: filters.q,
    countryId: filters.countryId,
    seriesId: filters.seriesId,
    sort: filters.sort,
    order: filters.order,
  });
  return api<CollectionPage>(`/collection${query}`);
}

export function fetchCollectionItem(id: number): Promise<CollectionItem> {
  return api<CollectionItem>(`/collection/${id}`);
}

/** One transaction on the server: the instance plus its coin_purchase expense. */
export function createCollectionItem(body: CollectionItemCreate): Promise<CollectionItem> {
  return api<CollectionItem>('/collection', { method: 'POST', body });
}

export function updateCollectionItem(
  id: number,
  body: CollectionItemUpdate,
): Promise<CollectionItem> {
  return api<CollectionItem>(`/collection/${id}`, { method: 'PATCH', body });
}

/** Deletes the linked purchase expense as well (docs/04-business-rules.md, rule 10). */
export function deleteCollectionItem(id: number): Promise<void> {
  return api<void>(`/collection/${id}`, { method: 'DELETE' });
}
