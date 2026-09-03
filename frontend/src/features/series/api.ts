import { api, toQuery } from '@/shared/api/client';
import type { SeriesProgress, SeriesSummary } from '@/shared/api/types';

/** Every series (of a country) with its completeness summary in one request. */
export function fetchSeriesProgress(countryId: number | undefined): Promise<SeriesProgress[]> {
  return api<SeriesProgress[]>(`/series/summary${toQuery({ countryId })}`);
}

export function fetchSeriesSummary(seriesId: number): Promise<SeriesSummary> {
  return api<SeriesSummary>(`/series/${seriesId}/summary`);
}
