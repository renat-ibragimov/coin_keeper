import { api, toQuery } from '@/shared/api/client';
import type { SeriesProgress } from '@/shared/api/types';

/** Every series (of a country) with its completeness summary in one request --
 *  the "Мої монети" dashboard's started/completed series widget. The
 *  "Комплектність" screen itself gets this from `/completeness/summary`
 *  (`features/completeness/api.ts`), grouped by an arbitrary field. */
export function fetchSeriesProgress(countryId: number | undefined): Promise<SeriesProgress[]> {
  return api<SeriesProgress[]>(`/series/summary${toQuery({ countryId })}`);
}
