import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { SearchX, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import type { CollectionGroup } from '@/shared/api/types';
import { useDismissable } from '@/shared/lib/useDismissable';
import { useStoredViewMode } from '@/shared/lib/useStoredViewMode';
import type { ActiveFilterChip } from '@/shared/ui';
import {
  Button,
  EmptyState,
  ErrorState,
  FiltersToolbar,
  GridIcon,
  PageHeader,
  Pagination,
  Skeleton,
  TableIcon,
} from '@/shared/ui';

import {
  fetchCatalog,
  fetchCatalogMaterials,
  fetchCountries,
  fetchDenominations,
  fetchSeries,
} from './api';
import { CatalogTable } from './CatalogTable';
import { CoinCard } from './CoinCard';
import { FiltersPanel } from './FiltersPanel';
import { parseFilters, SORT_FIELDS, useCatalogFilters } from './useCatalogFilters';
import type { CatalogFilters, CatalogView, SortField } from './useCatalogFilters';
import styles from './CatalogPage.module.css';

// The filters a fresh /catalog (no query string at all) starts from — reused
// as what the mobile drawer's own "Скинути" resets its draft to, since that
// reset must not touch the real, applied filters until "Застосувати" does
// (docs/08-ui-map.md: apply-on-confirm, phone only).
const EMPTY_FILTERS = parseFilters(new URLSearchParams());

const SORT_LABELS: Record<SortField, string> = {
  country: 'catalog.sortCountry',
  title: 'catalog.sortTitle',
  series: 'catalog.sortSeries',
  year: 'catalog.sortYear',
  denomination: 'catalog.sortDenomination',
  material: 'catalog.sortMaterial',
  owned: 'catalog.sortOwned',
  purchase: 'catalog.sortPurchase',
  price: 'catalog.sortPrice',
};

const GROUP_LABELS: Record<CollectionGroup, string> = {
  circulation: 'catalog.typeCirculation',
  commemorative: 'catalog.typeCommemorative',
  collector: 'catalog.typeCollector',
  other: 'catalog.typeOther',
};

// The catalog's own filter panel only ever offers a `catalog_confirmed`
// country's own facets (§13a) — narrowed further to one country when
// exactly one is picked, same as the single-select filters used to (a
// multi-country selection just shows the whole confirmed-scope list
// unnarrowed, owner's call, 2026-09-12).
function soleCountryId(countryIds: number[]): number | undefined {
  return countryIds.length === 1 ? countryIds[0] : undefined;
}

// A multiple of every column count the grid uses (1/2/3/5, see
// CatalogPage.module.css), so a full page always fills complete rows instead
// of stranding a short one before the pager.
const GRID_PAGE_SIZE = 30;

export function CatalogPage() {
  const { t } = useTranslation();
  const { filters, update, reset } = useCatalogFilters();

  // The phone's filters drawer edits this instead of the real, applied
  // filters directly — a field's own dropdown otherwise re-queried and
  // re-rendered the page under the visitor's thumb before they'd finished
  // picking a country, let alone gone on to its series and years. Opening
  // the drawer seeds it from the applied filters; only "Застосувати" copies
  // it across. The desktop filters bar is unaffected — it keeps applying
  // straight to `filters` below (docs/08-ui-map.md: apply-on-confirm, phone only).
  const [draft, setDraft] = useState<CatalogFilters>(filters);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The overlay handles the outside press itself; Escape and navigation come from the hook.
  useDismissable(drawerOpen, () => setDrawerOpen(false));
  const openDrawer = () => {
    setDraft(filters);
    setDrawerOpen(true);
  };
  const applyDraft = () => {
    update(draft);
    setDrawerOpen(false);
  };

  const [searchParams] = useSearchParams();
  const viewMode = useStoredViewMode('ck.viewMode.catalog');
  useEffect(() => {
    // Only on mount, and only when the URL itself says nothing: a shared
    // link's own `?view=` always wins over what was remembered here.
    const resolved = viewMode.resolve(searchParams.get('view') ?? undefined);
    if (resolved !== filters.view) update({ view: resolved, page: filters.page });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolve once, from the initial URL
  }, []);

  const catalogQuery = useQuery({
    queryKey: ['catalog', filters, GRID_PAGE_SIZE],
    queryFn: () => fetchCatalog(filters, GRID_PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const countriesQuery = useQuery({
    queryKey: ['countries', 'confirmed'],
    queryFn: () => fetchCountries('confirmed'),
  });
  const narrowCountryId = soleCountryId(filters.countryIds);
  const denominationsQuery = useQuery({
    queryKey: ['denominations', 'confirmed', narrowCountryId],
    queryFn: () => fetchDenominations(narrowCountryId, 'confirmed'),
  });
  const seriesQuery = useQuery({
    queryKey: ['series', 'catalog', narrowCountryId],
    queryFn: () => fetchSeries(narrowCountryId, 'catalog'),
  });
  const materialsQuery = useQuery({
    queryKey: ['catalog', 'materials', narrowCountryId],
    queryFn: () => fetchCatalogMaterials(narrowCountryId),
  });

  // The same series list already fetched for the "Серія" filter, keyed by
  // its display name so the card's series line can link to it without a
  // seriesId field on CatalogListItem or an extra request per card.
  const seriesIdByName = useMemo(
    () => Object.fromEntries((seriesQuery.data ?? []).map((series) => [series.name, series.id])),
    [seriesQuery.data],
  );

  const page = catalogQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / GRID_PAGE_SIZE));
  const shown = page ? page.items.length + (page.page - 1) * GRID_PAGE_SIZE : 0;

  // Shared between the real, applied filters and the drawer's own draft —
  // each chip's onRemove writes back through whichever `apply` it was built
  // with, so the same chip row works unchanged in both places.
  function buildChips(
    source: CatalogFilters,
    apply: (changes: Partial<CatalogFilters>) => void,
  ): ActiveFilterChip[] {
    const chips: ActiveFilterChip[] = [];
    if (source.q) {
      chips.push({ key: 'q', label: source.q, onRemove: () => apply({ q: '' }) });
    }
    for (const countryId of source.countryIds) {
      const country = (countriesQuery.data ?? []).find((c) => c.id === countryId);
      if (!country) continue;
      chips.push({
        key: `country-${countryId}`,
        label: country.name,
        onRemove: () => {
          const countryIds = source.countryIds.filter((id) => id !== countryId);
          // Removing a country invalidates the series, denomination and
          // material chosen under it too, same as changing the selection does.
          apply({ countryIds, seriesIds: [], denominationIds: [], materialIds: [] });
        },
      });
    }
    for (const seriesId of source.seriesIds) {
      const item = (seriesQuery.data ?? []).find((s) => s.id === seriesId);
      if (!item) continue;
      chips.push({
        key: `series-${seriesId}`,
        label: item.name,
        onRemove: () => apply({ seriesIds: source.seriesIds.filter((id) => id !== seriesId) }),
      });
    }
    if (source.yearFrom !== undefined || source.yearTo !== undefined) {
      chips.push({
        key: 'years',
        label: `${t('catalog.years')}: ${source.yearFrom ?? '…'}–${source.yearTo ?? '…'}`,
        onRemove: () => apply({ yearFrom: undefined, yearTo: undefined }),
      });
    }
    for (const denominationId of source.denominationIds) {
      const denomination = (denominationsQuery.data ?? []).find((d) => d.id === denominationId);
      if (!denomination) continue;
      chips.push({
        key: `denomination-${denominationId}`,
        label: denomination.label,
        onRemove: () =>
          apply({ denominationIds: source.denominationIds.filter((id) => id !== denominationId) }),
      });
    }
    for (const group of source.groups) {
      chips.push({
        key: `group-${group}`,
        label: t(GROUP_LABELS[group]),
        onRemove: () => apply({ groups: source.groups.filter((g) => g !== group) }),
      });
    }
    for (const materialId of source.materialIds) {
      const material = (materialsQuery.data ?? []).find((m) => m.id === materialId);
      if (!material) continue;
      chips.push({
        key: `material-${materialId}`,
        label: material.name,
        onRemove: () =>
          apply({ materialIds: source.materialIds.filter((id) => id !== materialId) }),
      });
    }
    if (source.owned !== undefined) {
      chips.push({
        key: 'owned',
        label: t(source.owned ? 'catalog.availabilityOwned' : 'catalog.availabilityMissing'),
        onRemove: () => apply({ owned: undefined }),
      });
    }
    return chips;
  }

  const activeChips = useMemo(
    () => buildChips(filters, update),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- buildChips closes over the queries below, not worth listing
    [
      filters,
      countriesQuery.data,
      seriesQuery.data,
      denominationsQuery.data,
      materialsQuery.data,
      update,
      t,
    ],
  );
  const draftChips = useMemo(
    () => buildChips(draft, (changes) => setDraft((current) => ({ ...current, ...changes }))),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- buildChips closes over the queries below, not worth listing
    [draft, countriesQuery.data, seriesQuery.data, denominationsQuery.data, materialsQuery.data, t],
  );

  const filtersPanel = (
    <FiltersPanel
      filters={filters}
      update={update}
      reset={reset}
      countries={countriesQuery.data ?? []}
      series={seriesQuery.data ?? []}
      seriesLoading={seriesQuery.isLoading}
      denominations={denominationsQuery.data ?? []}
      materials={materialsQuery.data ?? []}
      activeFilters={activeChips}
    />
  );

  const draftFiltersPanel = (
    <FiltersPanel
      filters={draft}
      update={(changes) => setDraft((current) => ({ ...current, ...changes }))}
      reset={() => setDraft(EMPTY_FILTERS)}
      countries={countriesQuery.data ?? []}
      series={seriesQuery.data ?? []}
      seriesLoading={seriesQuery.isLoading}
      denominations={denominationsQuery.data ?? []}
      materials={materialsQuery.data ?? []}
      activeFilters={draftChips}
    />
  );

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t('catalog.title')} subtitle={t('catalog.subtitle')} />

      <div className={styles.filtersBar}>{filtersPanel}</div>

      <section className={styles.content}>
        <FiltersToolbar<CatalogView>
          shown={shown}
          total={total}
          view={filters.view}
          viewOptions={[
            {
              value: 'cards',
              label: (
                <>
                  <GridIcon />
                  {t('catalog.viewCards')}
                </>
              ),
            },
            {
              value: 'table',
              label: (
                <>
                  <TableIcon />
                  {t('catalog.viewTable')}
                </>
              ),
            },
          ]}
          onViewChange={(view) => {
            update({ view, page: filters.page });
            viewMode.remember(view);
          }}
          sort={filters.sort}
          sortOptions={SORT_FIELDS.map((field) => ({ value: field, label: t(SORT_LABELS[field]) }))}
          onSortChange={(sort) => update({ sort: sort as SortField })}
          order={filters.order}
          onOrderChange={() => update({ order: filters.order === 'asc' ? 'desc' : 'asc' })}
          onOpenFilters={openDrawer}
        />

        {catalogQuery.isError ? (
          <ErrorState
            detail={
              catalogQuery.error instanceof ApiError && catalogQuery.error.status === 0
                ? t('errors.network')
                : undefined
            }
            onRetry={() => void catalogQuery.refetch()}
          />
        ) : null}

        {catalogQuery.isPending ? (
          <div className={styles.grid}>
            {Array.from({ length: 8 }, (_, index) => (
              <Skeleton key={index} height={280} />
            ))}
          </div>
        ) : null}

        {page && page.items.length === 0 ? (
          <EmptyState
            icon={<SearchX strokeWidth={1.75} />}
            title={t('catalog.emptyTitle')}
            description={t('catalog.emptyText')}
          />
        ) : null}

        {page && page.items.length > 0 ? (
          filters.view === 'cards' ? (
            <div className={styles.grid}>
              {page.items.map((item) => (
                <CoinCard key={item.id} item={item} seriesIdByName={seriesIdByName} />
              ))}
            </div>
          ) : (
            <CatalogTable items={page.items} filters={filters} update={update} />
          )
        ) : null}

        <Pagination
          page={filters.page}
          pageCount={pageCount}
          onChange={(next) => update({ page: next })}
        />
      </section>

      {drawerOpen ? (
        <div className={styles.drawerOverlay} onClick={() => setDrawerOpen(false)}>
          <div
            className={styles.drawer}
            role="dialog"
            aria-label={t('catalog.filters')}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHeader}>
              <button
                type="button"
                className={styles.drawerClose}
                onClick={() => setDrawerOpen(false)}
                aria-label={t('catalog.closeFilters')}
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>
            {draftFiltersPanel}
            <Button block onClick={applyDraft}>
              {t('catalog.applyFilters')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
