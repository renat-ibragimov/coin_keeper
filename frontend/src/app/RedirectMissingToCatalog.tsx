import { Navigate, useLocation } from 'react-router-dom';

import { parseFilters, serializeFilters } from '@/features/catalog/useCatalogFilters';

/**
 * The "missing" page is retired: the catalog's own "немає в колекції"
 * filter takes its place (docs/ui.md). Any filters bookmarked on the
 * old page (country, series, years — the page used the catalog's own filter
 * hook) share the catalog's query param vocabulary, so they carry over as-is;
 * `owned` is forced through the catalog's own serializer rather than a
 * hardcoded string, so it can never drift from what the catalog itself writes.
 */
export default function RedirectMissingToCatalog() {
  const location = useLocation();
  const params = serializeFilters({
    ...parseFilters(new URLSearchParams(location.search)),
    owned: false,
  });
  return (
    <Navigate
      to={{ pathname: '/catalog', search: `?${params.toString()}`, hash: location.hash }}
      replace
    />
  );
}
