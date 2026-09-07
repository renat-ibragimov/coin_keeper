import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Coins, Layers, TrendingUp, Wallet } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { fetchCountries, fetchDenominations, fetchSeries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { fetchSeriesProgress } from '@/features/series/api';
import { ApiError } from '@/shared/api/client';
import { useDismissable } from '@/shared/lib/useDismissable';
import { formatNumber, formatPercent, formatUah } from '@/shared/lib/format';
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

import { fetchCollection, PAGE_SIZE } from './api';
import { CollectionFiltersPanel } from './CollectionFiltersPanel';
import { PositionCard } from './PositionCard';
import { PositionTable } from './PositionTable';
import { COLLECTION_SORTS, hasActiveFilters, useCollectionFilters } from './useCollectionFilters';
import type { CollectionFilters, CollectionSort, CollectionView } from './useCollectionFilters';
import styles from './CollectionPage.module.css';

const SORT_LABELS: Record<CollectionSort, string> = {
  date: 'collection.sortDate',
  title: 'collection.sortTitle',
  total: 'collection.sortTotal',
};

const GROUP_LABELS: Record<NonNullable<CollectionFilters['group']>, string> = {
  circulation: 'catalog.typeCirculation',
  commemorative: 'catalog.typeCommemorative',
  collector: 'catalog.typeCollector',
  other: 'catalog.typeOther',
};

const METAL_LABELS: Record<NonNullable<CollectionFilters['metalKind']>, string> = {
  precious: 'catalog.metalPrecious',
  base: 'catalog.metalBase',
  unknown: 'catalog.metalUnknown',
};

export function CollectionPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const { filters, update, reset } = useCollectionFilters();
  const [drawerOpen, setDrawerOpen] = useState(false);
  useDismissable(drawerOpen, () => setDrawerOpen(false));

  const collectionQuery = useQuery({
    queryKey: ['collection', filters],
    queryFn: () => fetchCollection(filters),
    placeholderData: keepPreviousData,
  });
  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const seriesProgressQuery = useQuery({
    queryKey: ['series', 'progress', undefined],
    queryFn: () => fetchSeriesProgress(undefined),
  });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const seriesQuery = useQuery({
    queryKey: ['series', 'list', filters.countryId],
    queryFn: () => fetchSeries(filters.countryId),
  });
  const denominationsQuery = useQuery({
    queryKey: ['denominations', filters.countryId],
    queryFn: () => fetchDenominations(filters.countryId),
  });

  const page = collectionQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const shown = page ? page.items.length + (page.page - 1) * PAGE_SIZE : 0;
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

  const activeChips = useMemo(() => {
    const chips: ActiveFilterChip[] = [];
    if (filters.q) {
      chips.push({ key: 'q', label: filters.q, onRemove: () => update({ q: '' }) });
    }
    if (filters.countryId !== undefined) {
      const country = (countriesQuery.data ?? []).find((c) => c.id === filters.countryId);
      if (country) {
        chips.push({
          key: 'country',
          label: country.name,
          onRemove: () =>
            update({ countryId: undefined, seriesId: undefined, denominationId: undefined }),
        });
      }
    }
    if (filters.seriesId !== undefined) {
      const series = (seriesQuery.data ?? []).find((s) => s.id === filters.seriesId);
      if (series) {
        chips.push({
          key: 'series',
          label: series.name,
          onRemove: () => update({ seriesId: undefined }),
        });
      }
    }
    if (filters.yearFrom !== undefined || filters.yearTo !== undefined) {
      chips.push({
        key: 'years',
        label: `${t('catalog.years')}: ${filters.yearFrom ?? '…'}–${filters.yearTo ?? '…'}`,
        onRemove: () => update({ yearFrom: undefined, yearTo: undefined }),
      });
    }
    if (filters.denominationId !== undefined) {
      const denomination = (denominationsQuery.data ?? []).find(
        (d) => d.id === filters.denominationId,
      );
      if (denomination) {
        chips.push({
          key: 'denomination',
          label: denomination.label,
          onRemove: () => update({ denominationId: undefined }),
        });
      }
    }
    if (filters.group) {
      chips.push({
        key: 'group',
        label: t(GROUP_LABELS[filters.group]),
        onRemove: () => update({ group: undefined }),
      });
    }
    if (filters.metalKind) {
      chips.push({
        key: 'metal',
        label: t(METAL_LABELS[filters.metalKind]),
        onRemove: () => update({ metalKind: undefined }),
      });
    }
    if (filters.grade) {
      chips.push({
        key: 'grade',
        label: filters.grade,
        onRemove: () => update({ grade: undefined }),
      });
    }
    return chips;
  }, [filters, countriesQuery.data, seriesQuery.data, denominationsQuery.data, update, t]);

  const filtersPanel = (
    <CollectionFiltersPanel
      filters={filters}
      update={update}
      reset={reset}
      countries={countriesQuery.data ?? []}
      series={seriesQuery.data ?? []}
      seriesLoading={seriesQuery.isLoading}
      denominations={denominationsQuery.data ?? []}
      activeFilters={activeChips}
    />
  );

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        title={t('collection.title')}
        subtitle={t('collection.subtitle')}
        actions={
          <>
            <Link to="/collection/coins/new">
              <Button>+ {t('card.addPurchase')}</Button>
            </Link>
            <Link to="/import">
              <Button variant="ghost">{t('catalog.importUcoin')}</Button>
            </Link>
          </>
        }
      />

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

      {collectionEmpty ? (
        <EmptyState
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
        />
      ) : (
        <>
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
            onViewChange={(view) => update({ view, page: filters.page })}
            sort={filters.sort}
            sortOptions={COLLECTION_SORTS.map((sort) => ({
              value: sort,
              label: t(SORT_LABELS[sort]),
            }))}
            onSortChange={(sort) => update({ sort: sort as CollectionSort })}
            order={filters.order}
            onOrderChange={() => update({ order: filters.order === 'asc' ? 'desc' : 'asc' })}
            onOpenFilters={() => setDrawerOpen(true)}
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
            <EmptyState title={t('catalog.emptyTitle')} description={t('catalog.emptyText')} />
          ) : null}

          {page && page.items.length > 0 ? (
            filters.view === 'cards' ? (
              <div className={styles.grid}>
                {page.items.map((item) => (
                  <PositionCard key={item.catalogItemId} item={item} />
                ))}
              </div>
            ) : (
              <PositionTable items={page.items} />
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
                ✕
              </button>
            </div>
            {filtersPanel}
            <Button block onClick={() => setDrawerOpen(false)}>
              {t('catalog.applyFilters')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
