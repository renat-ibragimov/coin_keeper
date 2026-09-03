import { api, toQuery } from '@/shared/api/client';
import type { CatalogPage, CountryOut, DenominationOut } from '@/shared/api/types';

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
