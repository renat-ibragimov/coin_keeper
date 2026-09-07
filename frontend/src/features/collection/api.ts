import { api, toQuery } from '@/shared/api/client';
import type {
  CollectionItem,
  CollectionItemCreate,
  CollectionItemUpdate,
  CollectionPage,
  CountryOut,
  DenominationOut,
  SeriesOut,
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
    yearFrom: filters.yearFrom,
    yearTo: filters.yearTo,
    denominationId: filters.denominationId,
    group: filters.group,
    metalKind: filters.metalKind,
    grade: filters.grade,
    sort: filters.sort,
    order: filters.order,
  });
  return api<CollectionPage>(`/collection${query}`);
}

/** Countries the user actually owns a coin from — narrower than the
 *  catalog-wide `fetchCountries`, for the "Мої монети" filters panel. */
export function fetchOwnedCountries(): Promise<CountryOut[]> {
  return api<CountryOut[]>('/collection/countries');
}

export function fetchOwnedSeries(countryId?: number): Promise<SeriesOut[]> {
  return api<SeriesOut[]>(`/collection/series${toQuery({ countryId })}`);
}

export function fetchOwnedDenominations(countryId?: number): Promise<DenominationOut[]> {
  return api<DenominationOut[]>(`/collection/denominations${toQuery({ countryId })}`);
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
