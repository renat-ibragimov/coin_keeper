import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { fetchCatalog, fetchCountries, fetchSeries, PAGE_SIZE } from '@/features/catalog/api';
import { CoinCard } from '@/features/catalog/CoinCard';
import { parseFilters } from '@/features/catalog/useCatalogFilters';
import { ApiError } from '@/shared/api/client';
import { formatPercent, formatUah } from '@/shared/lib/format';
import {
  Breadcrumbs,
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Skeleton,
  StatTile,
} from '@/shared/ui';

import { fetchSeriesSummary } from './api';
import styles from './SeriesDetailPage.module.css';

export function SeriesDetailPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const { id } = useParams();
  const seriesId = Number.parseInt(id ?? '', 10);
  const valid = Number.isFinite(seriesId) && seriesId > 0;
  const [page, setPage] = useState(1);

  const seriesQuery = useQuery({
    queryKey: ['series', 'list', undefined],
    queryFn: () => fetchSeries(),
  });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: fetchCountries });
  const summaryQuery = useQuery({
    queryKey: ['series', 'summary', seriesId],
    queryFn: () => fetchSeriesSummary(seriesId),
    enabled: valid,
  });
  const itemsQuery = useQuery({
    queryKey: ['catalog', 'series-items', seriesId, page],
    queryFn: () =>
      fetchCatalog({ ...parseFilters(new URLSearchParams()), seriesId, sort: 'year', page }),
    enabled: valid,
    placeholderData: keepPreviousData,
  });

  const series = seriesQuery.data?.find((row) => row.id === seriesId);
  const country = countriesQuery.data?.find((row) => row.id === series?.countryId);
  const notFound =
    !valid ||
    (summaryQuery.error instanceof ApiError && summaryQuery.error.status === 404) ||
    (seriesQuery.data !== undefined && series === undefined);

  if (notFound) {
    return (
      <ErrorState
        title={t('series.notFound')}
        actions={
          <Link to="/series">
            <Button variant="secondary">{t('nav.series')}</Button>
          </Link>
        }
      />
    );
  }

  const summary = summaryQuery.data;
  const items = itemsQuery.data;
  const pageCount = Math.max(1, Math.ceil((items?.total ?? 0) / PAGE_SIZE));

  return (
    <div className={styles.page}>
      <PageHeader
        above={
          <Breadcrumbs
            items={[{ label: t('nav.series'), to: '/series' }, { label: series?.name ?? '…' }]}
          />
        }
        title={series?.name ?? <Skeleton width={280} height={36} />}
        subtitle={
          series
            ? [
                country?.name,
                series.startYear
                  ? `${series.startYear}${series.endYear ? `–${series.endYear}` : '–'}`
                  : null,
              ]
                .filter(Boolean)
                .join(' · ')
            : undefined
        }
        actions={
          series ? (
            <Link to={`/catalog?seriesId=${series.id}`}>
              <Button variant="secondary">{t('series.openInCatalog')}</Button>
            </Link>
          ) : undefined
        }
      />

      {series?.description ? <p className={styles.description}>{series.description}</p> : null}

      <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
        {summary ? (
          <>
            <StatTile
              label={t('series.collected')}
              value={t('dashboard.progress', { owned: summary.owned, count: summary.total })}
              hint={formatPercent(summary.completionPercent, locale, 1)}
            />
            <StatTile
              label={t('series.spent')}
              value={formatUah(summary.purchaseTotalUah, locale)}
            />
            <StatTile
              label={t('series.value')}
              value={formatUah(summary.currentValueUah, locale)}
            />
            <StatTile
              label={t('series.missing')}
              value={summary.missing}
              hint={
                summary.unpricedMissing > 0
                  ? t('dashboard.unpriced', { count: summary.unpricedMissing })
                  : undefined
              }
            />
          </>
        ) : (
          Array.from({ length: 4 }, (_, index) => <Skeleton key={index} height={96} />)
        )}
      </section>

      {itemsQuery.isError ? <ErrorState onRetry={() => void itemsQuery.refetch()} /> : null}
      {itemsQuery.isPending ? (
        <div className={styles.grid}>
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} height={300} />
          ))}
        </div>
      ) : null}
      {items && items.items.length === 0 ? (
        <EmptyState title={t('series.noItemsTitle')} description={t('series.noItemsText')} />
      ) : null}
      {items && items.items.length > 0 ? (
        <div className={styles.grid}>
          {items.items.map((item) => (
            <CoinCard
              key={item.id}
              item={item}
              action={
                item.quantityOwned === 0 ? (
                  <Link
                    to={`/collection/new?catalogItemId=${item.id}`}
                    state={{ from: `/series/${seriesId}` }}
                  >
                    <Button size="sm" variant="secondary">
                      + {t('card.addPurchase')}
                    </Button>
                  </Link>
                ) : undefined
              }
            />
          ))}
        </div>
      ) : null}
      <Pagination page={page} pageCount={pageCount} onChange={setPage} />
    </div>
  );
}
