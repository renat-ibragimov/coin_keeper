import { api, toQuery } from '@/shared/api/client';
import type { CatalogPage, CompletenessGroup, MetalKind } from '@/shared/api/types';

import type { CompletenessGroupBy } from './groupBy';

/** Either `value` (a real group) or `unassigned` (the "без значення" bucket)
 *  identifies a group -- exactly one of the two, never both. */
export type GroupSelector = { value: number } | { unassigned: true };

function selectorQuery(selector: GroupSelector) {
  return 'value' in selector ? { value: selector.value } : { unassigned: selector.unassigned };
}

/** Every group of the chosen dimension with its completeness summary in one
 *  request -- the "Комплектність" screen. */
export function fetchCompletenessSummary(
  groupBy: CompletenessGroupBy,
  countryId: number | undefined,
  metalKind: MetalKind | undefined,
): Promise<CompletenessGroup[]> {
  return api<CompletenessGroup[]>(
    `/completeness/summary${toQuery({ groupBy, countryId, metalKind })}`,
  );
}

/** One group's summary, for the detail screen's header -- works from a
 *  bookmarked/shared link without fetching the whole dimension's list. */
export function fetchCompletenessGroup(
  groupBy: CompletenessGroupBy,
  selector: GroupSelector,
  countryId: number | undefined,
): Promise<CompletenessGroup> {
  return api<CompletenessGroup>(
    `/completeness/group${toQuery({ groupBy, countryId, ...selectorQuery(selector) })}`,
  );
}

/** The detail screen's own tiles -- shared or personal, regardless of the
 *  country's catalog_confirmed (docs/04-business-rules.md §13a). Deliberately
 *  not `fetchCatalog(...)`: that's the catalogue browse experience's harder
 *  gate, which hides a user's own coins of a country the catalogue project
 *  hasn't confirmed yet. */
export function fetchCompletenessItems(
  groupBy: CompletenessGroupBy,
  selector: GroupSelector,
  countryId: number | undefined,
  page: number,
  pageSize: number,
): Promise<CatalogPage> {
  return api<CatalogPage>(
    `/completeness/items${toQuery({
      groupBy,
      countryId,
      page,
      pageSize,
      ...selectorQuery(selector),
    })}`,
  );
}
