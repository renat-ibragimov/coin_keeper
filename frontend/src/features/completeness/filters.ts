import type { MetalKind } from '@/shared/api/types';

// Only these two are ever a filterable choice -- 'unknown' is a display/
// groupBy bucket elsewhere (groupBy.ts), never something a user picks
// (same whitelist as the catalog's own metal-kind filter, useCatalogFilters.ts).
export function parseMetalKind(value: string | null): MetalKind | undefined {
  return value === 'precious' || value === 'base' ? value : undefined;
}

export function parseCountryId(value: string | null): number | undefined {
  return Number.parseInt(value ?? '', 10) || undefined;
}

/** The query string a group row's link carries from the list into its own
 * detail screen, so the numbers there match what the row just showed
 * (owner-reported, docs/ui.md: Комплектність). Scope ("Мої"/"Усі")
 * doesn't belong here -- it only decides which *rows* the list shows, and
 * has no meaning once you're already looking at one specific group. */
export function detailFilterQuery(countryId: number | undefined, metalKind: MetalKind | undefined) {
  const params = new URLSearchParams();
  if (countryId) params.set('countryId', String(countryId));
  if (metalKind) params.set('metalKind', metalKind);
  return params.toString();
}
