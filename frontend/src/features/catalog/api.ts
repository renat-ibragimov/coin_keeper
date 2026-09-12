import { api, toQuery } from '@/shared/api/client';
import type {
  CatalogCard,
  CatalogCollectionItem,
  CatalogPage,
  CoinMaterial,
  CountryOut,
  CurrencyOut,
  DenominationOut,
  PriceHistoryItem,
  SeriesOut,
} from '@/shared/api/types';

import type { CatalogFilters } from './useCatalogFilters';

export const PAGE_SIZE = 24;

export function fetchCatalog(
  filters: CatalogFilters,
  pageSize: number = PAGE_SIZE,
): Promise<CatalogPage> {
  const query = toQuery({
    page: filters.page,
    pageSize,
    q: filters.q,
    countryId: filters.countryIds,
    seriesId: filters.seriesIds,
    yearFrom: filters.yearFrom,
    yearTo: filters.yearTo,
    denominationId: filters.denominationIds,
    group: filters.groups,
    materialId: filters.materialIds,
    owned: filters.owned,
    scope: filters.scope === 'all' ? undefined : filters.scope,
    archived: filters.archived ? true : undefined,
    sort: filters.sort,
    order: filters.order,
  });
  return api<CatalogPage>(`/catalog${query}`);
}

/** `confirmed` is the catalog's own filter panel (only a `catalog_confirmed`
 *  country, §13a); `active` is the general storefront default; `all` is the
 *  personal-item form, where the user may enter a coin of any issuer ever. */
export function fetchCountries(
  scope: 'active' | 'all' | 'confirmed' = 'active',
): Promise<CountryOut[]> {
  return api<CountryOut[]>(
    `/countries${toQuery({ scope: scope === 'active' ? undefined : scope })}`,
  );
}

/** `scope=confirmed` is the catalog's own filter panel — only what a
 *  `catalog_confirmed` country offers (§13a). */
export function fetchDenominations(
  countryId: number | undefined,
  scope: 'all' | 'confirmed' = 'all',
): Promise<DenominationOut[]> {
  return api<DenominationOut[]>(
    `/denominations${toQuery({ countryId, scope: scope === 'all' ? undefined : scope })}`,
  );
}

/** Materials the catalog's material filter offers — only what a
 *  `catalog_confirmed` item actually uses (§14). */
export function fetchCatalogMaterials(countryId?: number): Promise<CoinMaterial[]> {
  return api<CoinMaterial[]>(`/catalog/materials${toQuery({ countryId })}`);
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

/** `scope=catalog` is the catalog's own filter panel — only a
 *  `catalog_confirmed` country's series, no exception for one the user owns
 *  coins in (§13a). `scope=mine` (default) is every other caller: the
 *  standalone "Серії" screen and the dashboard, unrestricted. */
export function fetchSeries(
  countryId?: number,
  scope: 'mine' | 'catalog' = 'mine',
): Promise<SeriesOut[]> {
  return api<SeriesOut[]>(
    `/series${toQuery({ countryId, scope: scope === 'mine' ? undefined : scope })}`,
  );
}

export function fetchCurrencies(): Promise<CurrencyOut[]> {
  return api<CurrencyOut[]>('/currencies');
}

/** Quick lookup for pickers: a handful of active items matching the text. */
export function searchCatalog(q: string, limit = 8): Promise<CatalogPage> {
  return api<CatalogPage>(`/catalog${toQuery({ q, page: 1, pageSize: limit })}`);
}
