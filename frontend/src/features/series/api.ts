import { api, toQuery } from '@/shared/api/client';
import type { CatalogPage, SeriesProgress, SeriesSummary } from '@/shared/api/types';

/** Every series (of a country) with its completeness summary in one request. */
export function fetchSeriesProgress(countryId: number | undefined): Promise<SeriesProgress[]> {
  return api<SeriesProgress[]>(`/series/summary${toQuery({ countryId })}`);
}

export function fetchSeriesSummary(seriesId: number): Promise<SeriesSummary> {
  return api<SeriesSummary>(`/series/${seriesId}/summary`);
}

/** The series detail screen's own tiles — shared or personal, regardless of
 *  the country's catalog_confirmed (docs/04-business-rules.md §13a).
 *  Deliberately not `fetchCatalog({seriesIds: [id]})`: that's the catalogue
 *  browse experience's harder gate, which hides a user's own coins of a
 *  country the catalogue project hasn't confirmed yet. */
export function fetchSeriesItems(
  seriesId: number,
  page: number,
  pageSize: number,
): Promise<CatalogPage> {
  return api<CatalogPage>(`/series/${seriesId}/items${toQuery({ page, pageSize })}`);
}
