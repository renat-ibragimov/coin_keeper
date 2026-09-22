import { api, toQuery } from '@/shared/api/client';
import { periodToYearRange } from '@/shared/lib/periodFilter';
import type {
  CoinMaterial,
  CollectionItem,
  CollectionItemCreate,
  CollectionItemPhotos,
  CollectionItemUpdate,
  CollectionPage,
  CountryOut,
  DenominationOut,
  SeriesOut,
  StorageLocation,
} from '@/shared/api/types';

export type PhotoRole = 'obverse' | 'reverse';

import type { CollectionFilters } from './useCollectionFilters';

export const PAGE_SIZE = 24;

export function fetchCollection(
  filters: CollectionFilters,
  pageSize: number = PAGE_SIZE,
): Promise<CollectionPage> {
  const { yearFrom, yearTo } = periodToYearRange(filters.period);
  const query = toQuery({
    page: filters.page,
    pageSize,
    q: filters.q,
    countryId: filters.countryIds,
    seriesId: filters.seriesIds,
    yearFrom,
    yearTo,
    denominationId: filters.denominationIds,
    group: filters.groups,
    materialId: filters.materialIds,
    metalKind: filters.metalKinds,
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

/** Materials the user actually owns a coin of — for the "Мої монети" filters
 *  panel's material multi-select. */
export function fetchOwnedMaterials(countryId?: number): Promise<CoinMaterial[]> {
  return api<CoinMaterial[]>(`/collection/materials${toQuery({ countryId })}`);
}

/** Presets plus this owner's own, localized names — for the purchase form's
 *  storage-location suggestions and the settings page's management list. A
 *  name is a free-form suggestion, not an id the client has to track: a new
 *  one is created server-side the moment it is used (docs/04-business-rules.md).
 *  `custom` marks the ones the owner added themselves — only those delete. */
export function fetchStorageLocations(): Promise<StorageLocation[]> {
  return api<StorageLocation[]>('/collection/storage-locations');
}

/** Explicit "add to my list" from settings — the same find-or-create a
 *  purchase's own storage location field triggers implicitly. */
export function addStorageLocation(name: string): Promise<StorageLocation> {
  return api<StorageLocation>('/collection/storage-locations', { method: 'POST', body: { name } });
}

/** 403 if `name` is one of the four shared presets — those cannot be
 *  deleted by any single account. */
export function deleteStorageLocation(name: string): Promise<void> {
  return api<void>(`/collection/storage-locations${toQuery({ name })}`, { method: 'DELETE' });
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

/** Raw bytes, not multipart — same shape as PUT /auth/me/avatar. Answers with
 *  both sides of the instance, already resolved, so the page repaints without
 *  a second request. */
export function uploadCoinPhoto(
  itemId: number,
  role: PhotoRole,
  image: Blob,
): Promise<CollectionItemPhotos> {
  return api<CollectionItemPhotos>(`/collection/${itemId}/photos/${role}`, {
    method: 'PUT',
    body: image,
  });
}

export function deleteCoinPhoto(itemId: number, role: PhotoRole): Promise<CollectionItemPhotos> {
  return api<CollectionItemPhotos>(`/collection/${itemId}/photos/${role}`, { method: 'DELETE' });
}
