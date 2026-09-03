import { api, toQuery } from '@/shared/api/client';
import type {
  CatalogCard,
  CatalogCollectionItem,
  CatalogItemCreate,
  CatalogPage,
  CountryOut,
  CurrencyOut,
  DenominationOut,
  PriceHistoryItem,
  SeriesOut,
} from '@/shared/api/types';

import type { CatalogFilters } from './useCatalogFilters';

export const PAGE_SIZE = 24;

export function fetchCatalog(filters: CatalogFilters): Promise<CatalogPage> {
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
    owned: filters.owned,
    scope: filters.scope === 'all' ? undefined : filters.scope,
    archived: filters.archived ? true : undefined,
    sort: filters.sort,
    order: filters.order,
  });
  return api<CatalogPage>(`/catalog${query}`);
}

export function fetchCountries(): Promise<CountryOut[]> {
  return api<CountryOut[]>('/countries');
}

export function fetchDenominations(countryId: number | undefined): Promise<DenominationOut[]> {
  return api<DenominationOut[]>(`/denominations${toQuery({ countryId })}`);
}

export function fetchCard(itemId: number): Promise<CatalogCard> {
  return api<CatalogCard>(`/catalog/${itemId}`);
}

/** Snapshots visible to the user, newest first (shared ones plus their own). */
export function fetchPrices(itemId: number): Promise<PriceHistoryItem[]> {
  return api<PriceHistoryItem[]>(`/catalog/${itemId}/prices`);
}

/** The current user's instances of one catalog item. */
export function fetchOwnInstances(itemId: number): Promise<CatalogCollectionItem[]> {
  return api<CatalogCollectionItem[]>(`/catalog/${itemId}/collection-items`);
}

export function fetchSeries(countryId?: number): Promise<SeriesOut[]> {
  return api<SeriesOut[]>(`/series${toQuery({ countryId })}`);
}

export function fetchCurrencies(): Promise<CurrencyOut[]> {
  return api<CurrencyOut[]>('/currencies');
}

export function createCatalogItem(body: CatalogItemCreate): Promise<CatalogCard> {
  return api<CatalogCard>('/catalog', { method: 'POST', body });
}
