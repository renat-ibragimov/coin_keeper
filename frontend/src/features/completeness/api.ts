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
 *  bookmarked/shared link without fetching the whole dimension's list.
 *  `metalKind` matches whatever the list's own filter was set to, so the
 *  numbers on the detail screen agree with the row the user clicked
 *  (docs/ui.md, "Completeness"). */
export function fetchCompletenessGroup(
  groupBy: CompletenessGroupBy,
  selector: GroupSelector,
  countryId: number | undefined,
  metalKind: MetalKind | undefined,
): Promise<CompletenessGroup> {
  return api<CompletenessGroup>(
    `/completeness/group${toQuery({ groupBy, countryId, metalKind, ...selectorQuery(selector) })}`,
  );
}

/** The detail screen's own tiles -- shared or personal, regardless of the
 *  country's catalog_confirmed (docs/business-rules.md, BR-13a). Deliberately
 *  not `fetchCatalog(...)`: that's the catalogue browse experience's harder
 *  gate, which hides a user's own coins of a country the catalogue project
 *  hasn't confirmed yet. `owned` is the detail screen's own filter (narrows
 *  the grid to what's collected or to what's missing), independent of the
 *  list's scope tab, which has no meaning once a single group is open. */
export function fetchCompletenessItems(
  groupBy: CompletenessGroupBy,
  selector: GroupSelector,
  countryId: number | undefined,
  metalKind: MetalKind | undefined,
  owned: boolean | undefined,
  page: number,
  pageSize: number,
): Promise<CatalogPage> {
  return api<CatalogPage>(
    `/completeness/items${toQuery({
      groupBy,
      countryId,
      metalKind,
      owned,
      page,
      pageSize,
      ...selectorQuery(selector),
    })}`,
  );
}
