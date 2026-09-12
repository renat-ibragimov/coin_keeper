import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Coins, Layers, SearchX, TrendingUp, Wallet, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { fetchBootstrap } from '@/features/dashboard/api';
import { fetchSeriesProgress } from '@/features/series/api';
import { ApiError } from '@/shared/api/client';
import type { CollectionGroup } from '@/shared/api/types';
import { useDismissable } from '@/shared/lib/useDismissable';
import { formatNumber, formatPercent, formatUah } from '@/shared/lib/format';
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
  StatTile,
  TableIcon,
} from '@/shared/ui';

import {
  fetchCollection,
  fetchOwnedCountries,
  fetchOwnedDenominations,
  fetchOwnedMaterials,
  fetchOwnedSeries,
} from './api';
import { CollectionFiltersPanel } from './CollectionFiltersPanel';
import { PositionCard } from './PositionCard';
import { PositionTable } from './PositionTable';
import {
  COLLECTION_SORTS,
  hasActiveFilters,
  parseCollectionFilters,
  useCollectionFilters,
} from './useCollectionFilters';
import type { CollectionFilters, CollectionSort, CollectionView } from './useCollectionFilters';
import styles from './CollectionPage.module.css';

// The filters a fresh /collection/coins (no query string at all) starts
// from — reused as what the mobile drawer's own "Скинути" resets its draft
// to, since that reset must not touch the real, applied filters until
// "Застосувати" does (docs/08-ui-map.md: apply-on-confirm, phone only).
const EMPTY_FILTERS = parseCollectionFilters(new URLSearchParams());

// Fixed column counts (1/2/3/5, CollectionPage.module.css) rather than an
// auto-fill fluid grid: each one divides this evenly, so every page fills
// complete rows instead of stranding a short one before the pager (same
// fix as CatalogPage.tsx's GRID_PAGE_SIZE).
const GRID_PAGE_SIZE = 30;

const SORT_LABELS: Record<CollectionSort, string> = {
  title: 'collection.sortTitle',
  country: 'catalog.sortCountry',
  series: 'catalog.sortSeries',
  quantity: 'collection.sortQuantity',
  total: 'collection.sortTotal',
  valuation: 'collection.sortValuation',
  date: 'collection.sortDate',
  grade: 'collection.sortGrade',
};

const GROUP_LABELS: Record<CollectionGroup, string> = {
  circulation: 'catalog.typeCirculation',
  commemorative: 'catalog.typeCommemorative',
  collector: 'catalog.typeCollector',
  other: 'catalog.typeOther',
};

export function CollectionPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const { filters, update, reset } = useCollectionFilters();

  // The phone's filters drawer edits this instead of the real, applied
  // filters directly — see CatalogPage.tsx for why. The desktop filters bar
  // is unaffected — it keeps applying straight to `filters` below
  // (docs/08-ui-map.md: apply-on-confirm, phone only).
  const [draft, setDraft] = useState<CollectionFilters>(filters);
  const [drawerOpen, setDrawerOpen] = useState(false);
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
  const viewMode = useStoredViewMode('ck.viewMode.collection');
  useEffect(() => {
    // Only on mount, and only when the URL itself says nothing: a shared
    // link's own `?view=` always wins over what was remembered here.
    const resolved = viewMode.resolve(searchParams.get('view') ?? undefined);
    if (resolved !== filters.view) update({ view: resolved, page: filters.page });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resolve once, from the initial URL
  }, []);

  const collectionQuery = useQuery({
    queryKey: ['collection', filters, GRID_PAGE_SIZE],
    queryFn: () => fetchCollection(filters, GRID_PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const seriesProgressQuery = useQuery({
    queryKey: ['series', 'progress', undefined],
    queryFn: () => fetchSeriesProgress(undefined),
  });
  // Scoped to what the user actually owns — not the catalog-wide reference
  // lists (docs/03-api-contract.md), so the key namespace differs from the
  // catalog's own ['countries']/['series', ...]/['denominations', ...].
  const countriesQuery = useQuery({
    queryKey: ['collection', 'countries'],
    queryFn: () => fetchOwnedCountries(),
  });
  // The panel only ever narrows against one country's own facets — a
  // multi-country selection just shows the whole owned-scope list unnarrowed
  // (same call as the catalog's own soleCountryId, CatalogPage.tsx).
  const narrowCountryId = filters.countryIds.length === 1 ? filters.countryIds[0] : undefined;
  const seriesQuery = useQuery({
    queryKey: ['collection', 'series', narrowCountryId],
    queryFn: () => fetchOwnedSeries(narrowCountryId),
  });
  const denominationsQuery = useQuery({
    queryKey: ['collection', 'denominations', narrowCountryId],
    queryFn: () => fetchOwnedDenominations(narrowCountryId),
  });
  const materialsQuery = useQuery({
    queryKey: ['collection', 'materials', narrowCountryId],
    queryFn: () => fetchOwnedMaterials(narrowCountryId),
  });

  const page = collectionQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / GRID_PAGE_SIZE));
  const shown = page ? page.items.length + (page.page - 1) * GRID_PAGE_SIZE : 0;
  const dashboard = bootstrapQuery.data?.dashboard;
  const seriesStats = seriesProgressQuery.data
    ? {
        started: seriesProgressQuery.data.filter((row) => row.summary.owned > 0).length,
        completed: seriesProgressQuery.data.filter(
          (row) => row.summary.total > 0 && row.summary.owned === row.summary.total,
        ).length,
      }
    : null;
  // docs/03-api-contract.md: emptiness is the server's isEmpty from bootstrap
  // (no coins and no personal items), not a locally derived "zero rows" guess.
  const collectionEmpty = dashboard?.isEmpty === true && !hasActiveFilters(filters);

  // Shared between the real, applied filters and the drawer's own draft —
  // each chip's onRemove writes back through whichever `apply` it was built
  // with, so the same chip row works unchanged in both places.
  function buildChips(
    source: CollectionFilters,
    apply: (changes: Partial<CollectionFilters>) => void,
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
          apply({ countryIds, seriesIds: [], denominationIds: [], materialIds: [] });
        },
      });
    }
    for (const seriesId of source.seriesIds) {
      const series = (seriesQuery.data ?? []).find((s) => s.id === seriesId);
      if (!series) continue;
      chips.push({
        key: `series-${seriesId}`,
        label: series.name,
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
    if (source.grade) {
      chips.push({
        key: 'grade',
        label: source.grade,
        onRemove: () => apply({ grade: undefined }),
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
    <CollectionFiltersPanel
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
    <CollectionFiltersPanel
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
      <PageHeader
        align="center"
        title={t('collection.title')}
        subtitle={t('collection.subtitle')}
        actions={
          collectionEmpty ? undefined : (
            <>
              <Link to="/collection/coins/new">
                <Button>+ {t('card.addPurchase')}</Button>
              </Link>
              <Link to="/import">
                <Button variant="ghost">{t('catalog.importUcoin')}</Button>
              </Link>
            </>
          )
        }
      />

      {collectionEmpty ? (
        <EmptyState
          variant="card"
          icon={<Coins strokeWidth={1.75} />}
          title={t('collection.emptyTitle')}
          description={t('collection.emptyText')}
          actions={
            <>
              <Link to="/catalog">
                <Button>{t('common.backToCatalog')}</Button>
              </Link>
              <Link to="/collection/coins/new">
                <Button variant="secondary">{t('card.addPurchase')}</Button>
              </Link>
            </>
          }
          note={<Link to="/import">{t('catalog.importUcoin')}</Link>}
        />
      ) : (
        <>
          <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
            {dashboard ? (
              <>
                <StatTile
                  icon={<Coins strokeWidth={1.75} />}
                  label={t('collection.tileCoins')}
                  value={formatNumber(dashboard.collectionItems, locale, 0)}
                  hint={t('dashboard.tileCoinsHint', { count: dashboard.completedItems })}
                />
                <StatTile
                  icon={<Wallet strokeWidth={1.75} />}
                  label={t('collection.tileSpent')}
                  value={formatUah(dashboard.coinSpendUah, locale)}
                  hint={t('collection.tileSpentHint', {
                    total: formatUah(dashboard.totalSpendUah, locale),
                  })}
                />
                <StatTile
                  icon={<TrendingUp strokeWidth={1.75} />}
                  label={t('collection.tileValue')}
                  value={formatUah(dashboard.marketValueUah, locale)}
                  hint={t('collection.tileValueHint')}
                />
                <StatTile
                  icon={<Layers strokeWidth={1.75} />}
                  label={t('collection.tileSeries')}
                  value={
                    seriesStats ? (
                      `${seriesStats.completed} / ${seriesStats.started}`
                    ) : (
                      <Skeleton width={60} />
                    )
                  }
                  hint={
                    seriesStats && seriesStats.started > 0
                      ? formatPercent((seriesStats.completed / seriesStats.started) * 100, locale)
                      : t('collection.tileSeriesHint')
                  }
                />
              </>
            ) : (
              Array.from({ length: 4 }, (_, index) => <Skeleton key={index} height={96} />)
            )}
          </section>

          <div className={styles.filtersBar}>{filtersPanel}</div>

          <FiltersToolbar<CollectionView>
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
            sortOptions={COLLECTION_SORTS.map((sort) => ({
              value: sort,
              label: t(SORT_LABELS[sort]),
            }))}
            onSortChange={(sort) => update({ sort: sort as CollectionSort })}
            order={filters.order}
            onOrderChange={() => update({ order: filters.order === 'asc' ? 'desc' : 'asc' })}
            onOpenFilters={openDrawer}
          />

          {collectionQuery.isError ? (
            <ErrorState
              detail={
                collectionQuery.error instanceof ApiError && collectionQuery.error.status === 0
                  ? t('errors.network')
                  : undefined
              }
              onRetry={() => void collectionQuery.refetch()}
            />
          ) : null}

          {collectionQuery.isPending ? (
            <div className={styles.grid}>
              {Array.from({ length: 8 }, (_, index) => (
                <Skeleton key={index} height={360} />
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
                  <PositionCard key={item.catalogItemId} item={item} />
                ))}
              </div>
            ) : (
              <PositionTable
                items={page.items}
                sort={filters.sort}
                order={filters.order}
                onSort={(sort, order) => update({ sort, order })}
              />
            )
          ) : null}

          <Pagination
            page={filters.page}
            pageCount={pageCount}
            onChange={(next) => update({ page: next })}
          />
        </>
      )}

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
