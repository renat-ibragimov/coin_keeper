import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { fetchCountries, fetchSeries, PAGE_SIZE } from '@/features/catalog/api';
import { CoinCard } from '@/features/catalog/CoinCard';
import { ApiError } from '@/shared/api/client';
import { formatPercent, formatUah } from '@/shared/lib/format';
import {
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Skeleton,
  StatTile,
} from '@/shared/ui';

import { fetchSeriesItems, fetchSeriesSummary } from './api';
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
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const summaryQuery = useQuery({
    queryKey: ['series', 'summary', seriesId],
    queryFn: () => fetchSeriesSummary(seriesId),
    enabled: valid,
  });
  const itemsQuery = useQuery({
    queryKey: ['series', 'items', seriesId, page],
    queryFn: () => fetchSeriesItems(seriesId, page, PAGE_SIZE),
    enabled: valid,
    placeholderData: keepPreviousData,
  });

  const series = seriesQuery.data?.find((row) => row.id === seriesId);
  const seriesIdByName = useMemo(
    () => Object.fromEntries((seriesQuery.data ?? []).map((row) => [row.name, row.id])),
    [seriesQuery.data],
  );
  const country = countriesQuery.data?.find((row) => row.id === series?.countryId);
  // Neither "confirmed" nor "not confirmed" is the right guess while this is
  // still loading -- rendering nothing until it's known avoids a flash from
  // one to the other (docs/04-business-rules.md, §13a).
  const confirmedKnown = countriesQuery.data !== undefined && series !== undefined;
  const catalogConfirmed = country?.catalogConfirmed === true;
  const notFound =
    !valid ||
    (summaryQuery.error instanceof ApiError && summaryQuery.error.status === 404) ||
    (seriesQuery.data !== undefined && series === undefined);

  if (notFound) {
    return (
      <ErrorState
        title={t('series.notFound')}
        actions={
          <Link to="/collection/series">
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
        align="center"
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
          series && confirmedKnown && catalogConfirmed ? (
            <Link to={`/catalog?seriesId=${series.id}`}>
              <Button variant="secondary">{t('series.openInCatalog')}</Button>
            </Link>
          ) : undefined
        }
      />

      {confirmedKnown && !catalogConfirmed ? (
        <p className={styles.notConfirmedNotice}>{t('series.notInCatalogNotice')}</p>
      ) : null}

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
              backTo={`/collection/series/${seriesId}`}
              seriesIdByName={seriesIdByName}
            />
          ))}
        </div>
      ) : null}
      <Pagination page={page} pageCount={pageCount} onChange={setPage} />
    </div>
  );
}
