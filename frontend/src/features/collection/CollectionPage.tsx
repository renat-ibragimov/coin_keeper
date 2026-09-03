import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { fetchCountries, fetchSeries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { fetchSeriesProgress } from '@/features/series/api';
import { ApiError } from '@/shared/api/client';
import type { CollectionItem } from '@/shared/api/types';
import { formatNumber, formatPercent, formatUah } from '@/shared/lib/format';
import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
  StatTile,
  Tabs,
} from '@/shared/ui';

import { fetchCollection, PAGE_SIZE } from './api';
import { DeleteInstanceDialog } from './DeleteInstanceDialog';
import { InstanceCard } from './InstanceCard';
import { InstanceTable } from './InstanceTable';
import { COLLECTION_SORTS, hasActiveFilters, useCollectionFilters } from './useCollectionFilters';
import type { CollectionSort, CollectionView } from './useCollectionFilters';
import styles from './CollectionPage.module.css';

const SORT_LABELS: Record<CollectionSort, string> = {
  date: 'collection.sortDate',
  title: 'collection.sortTitle',
  total: 'collection.sortTotal',
};

export function CollectionPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const { filters, update, reset } = useCollectionFilters();
  const [deleting, setDeleting] = useState<CollectionItem | null>(null);

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
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: fetchCountries });
  const seriesQuery = useQuery({
    queryKey: ['series', 'list', filters.countryId],
    queryFn: () => fetchSeries(filters.countryId),
  });

  // Search is debounced before it touches the URL.
  const [search, setSearch] = useState(filters.q);
  useEffect(() => setSearch(filters.q), [filters.q]);
  useEffect(() => {
    if (search === filters.q) return;
    const timer = setTimeout(() => update({ q: search }), 400);
    return () => clearTimeout(timer);
  }, [search, filters.q, update]);

  const page = collectionQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const dashboard = bootstrapQuery.data?.dashboard;
  const seriesStats = seriesProgressQuery.data
    ? {
        started: seriesProgressQuery.data.filter((row) => row.summary.owned > 0).length,
        completed: seriesProgressQuery.data.filter(
          (row) => row.summary.total > 0 && row.summary.owned === row.summary.total,
        ).length,
      }
    : null;
  const collectionEmpty = page !== undefined && total === 0 && !hasActiveFilters(filters);

  return (
    <div className={styles.page}>
      <PageHeader
        title={t('collection.title')}
        subtitle={t('collection.subtitle')}
        actions={
          <Link to="/collection/new">
            <Button>+ {t('card.addPurchase')}</Button>
          </Link>
        }
      />

      <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
        {dashboard ? (
          <>
            <StatTile
              icon="◎"
              label={t('collection.tileCoins')}
              value={formatNumber(dashboard.collectionItems, locale, 0)}
              hint={t('dashboard.tileCoinsHint', { count: dashboard.completedItems })}
            />
            <StatTile
              icon="◇"
              label={t('collection.tileSpent')}
              value={formatUah(dashboard.coinSpendUah, locale)}
              hint={t('collection.tileSpentHint', {
                total: formatUah(dashboard.totalSpendUah, locale),
              })}
            />
            <StatTile
              icon="↗"
              label={t('collection.tileValue')}
              value={formatUah(dashboard.marketValueUah, locale)}
              hint={t('collection.tileValueHint')}
            />
            <StatTile
              icon="◔"
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
          icon="◎"
          title={t('collection.emptyTitle')}
          description={t('collection.emptyText')}
          actions={
            <>
              <Link to="/catalog">
                <Button>{t('common.backToCatalog')}</Button>
              </Link>
              <Link to="/collection/new">
                <Button variant="secondary">{t('card.addPurchase')}</Button>
              </Link>
            </>
          }
        />
      ) : (
        <>
          <div className={styles.toolbar}>
            <Input
              type="search"
              placeholder={t('collection.searchPlaceholder')}
              aria-label={t('collection.searchPlaceholder')}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className={styles.search}
            />
            <Select
              aria-label={t('catalog.country')}
              value={filters.countryId ?? ''}
              onChange={(event) => update({ countryId: Number(event.target.value) || undefined })}
            >
              <option value="">{t('catalog.allCountries')}</option>
              {(countriesQuery.data ?? []).map((country) => (
                <option key={country.id} value={country.id}>
                  {country.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label={t('catalog.tableSeries')}
              value={filters.seriesId ?? ''}
              onChange={(event) => update({ seriesId: Number(event.target.value) || undefined })}
            >
              <option value="">{t('collection.allSeries')}</option>
              {(seriesQuery.data ?? []).map((series) => (
                <option key={series.id} value={series.id}>
                  {series.name}
                </option>
              ))}
            </Select>
            <span className={styles.sortControls}>
              <Select
                aria-label={t('catalog.sort')}
                value={filters.sort}
                onChange={(event) => update({ sort: event.target.value as CollectionSort })}
              >
                {COLLECTION_SORTS.map((sort) => (
                  <option key={sort} value={sort}>
                    {t(SORT_LABELS[sort])}
                  </option>
                ))}
              </Select>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => update({ order: filters.order === 'asc' ? 'desc' : 'asc' })}
                aria-label={
                  filters.order === 'asc' ? t('catalog.orderAsc') : t('catalog.orderDesc')
                }
                title={filters.order === 'asc' ? t('catalog.orderAsc') : t('catalog.orderDesc')}
              >
                {filters.order === 'asc' ? '↑' : '↓'}
              </Button>
            </span>
            <Tabs<CollectionView>
              aria-label={t('catalog.viewLabel')}
              options={[
                { value: 'cards', label: t('catalog.viewCards') },
                { value: 'list', label: t('collection.viewList') },
              ]}
              value={filters.view}
              onChange={(view) => update({ view, page: filters.page })}
            />
          </div>

          <div className={styles.counter}>
            <span className="tabular">
              {t('pagination.shown', {
                shown: page ? page.items.length + (page.page - 1) * PAGE_SIZE : 0,
                total,
              })}
            </span>
            {hasActiveFilters(filters) ? (
              <Button variant="ghost" size="sm" onClick={reset}>
                ↺ {t('catalog.resetFilters')}
              </Button>
            ) : null}
          </div>

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
                  <InstanceCard key={item.id} item={item} onDelete={setDeleting} />
                ))}
              </div>
            ) : (
              <InstanceTable items={page.items} onDelete={setDeleting} />
            )
          ) : null}

          <Pagination
            page={filters.page}
            pageCount={pageCount}
            onChange={(next) => update({ page: next })}
          />
        </>
      )}

      <DeleteInstanceDialog item={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}
