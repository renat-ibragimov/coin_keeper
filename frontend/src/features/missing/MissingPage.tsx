import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { fetchCatalog, fetchCountries, fetchSeries, PAGE_SIZE } from '@/features/catalog/api';
import { CoinCard } from '@/features/catalog/CoinCard';
import { useCatalogFilters } from '@/features/catalog/useCatalogFilters';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import { formatNumber, formatUah } from '@/shared/lib/format';
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
} from '@/shared/ui';

import styles from './MissingPage.module.css';

/**
 * /missing — catalog items the user has no instance of, with the catalog
 * filters (country, series, years). Its own screen rather than a catalog
 * filter, as docs/08-ui-map.md asks; the listing is GET /catalog?owned=false.
 */
export function MissingPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const location = useLocation();
  const { filters, update, reset } = useCatalogFilters();
  const query = { ...filters, owned: false as const, archived: false, scope: 'all' as const };

  const itemsQuery = useQuery({
    queryKey: ['catalog', 'missing', query],
    queryFn: () => fetchCatalog(query),
    placeholderData: keepPreviousData,
  });
  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const seriesQuery = useQuery({
    queryKey: ['series', 'list', filters.countryId],
    queryFn: () => fetchSeries(filters.countryId),
  });

  const page = itemsQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const dashboard = bootstrapQuery.data?.dashboard;
  const narrowed = Boolean(
    filters.countryId || filters.seriesId || filters.yearFrom || filters.yearTo,
  );
  const numberOrUndefined = (raw: string) => {
    const value = Number.parseInt(raw, 10);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  };
  const backTo = `${location.pathname}${location.search}`;

  return (
    <div className={styles.page}>
      <PageHeader title={t('missing.title')} subtitle={t('missing.subtitle')} />

      <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
        <StatTile
          label={narrowed ? t('missing.tileFiltered') : t('missing.tileAll')}
          value={page ? formatNumber(total, locale, 0) : <Skeleton width={60} />}
          hint={
            narrowed && dashboard
              ? t('missing.tileAllHint', { count: dashboard.missingItems })
              : undefined
          }
        />
        <StatTile
          label={t('missing.tileUnpriced')}
          value={
            dashboard ? (
              formatNumber(dashboard.unpricedMissingItems, locale, 0)
            ) : (
              <Skeleton width={60} />
            )
          }
          hint={t('missing.wholeCatalog')}
        />
        <StatTile
          label={t('missing.tileBudget')}
          value={
            dashboard ? formatUah(dashboard.missingBudgetUah, locale) : <Skeleton width={90} />
          }
          hint={t('missing.wholeCatalog')}
        />
      </section>

      <div className={styles.toolbar}>
        <Select
          aria-label={t('catalog.country')}
          value={filters.countryId ?? ''}
          onChange={(event) =>
            update({ countryId: Number(event.target.value) || undefined, seriesId: undefined })
          }
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
        <div className={styles.years}>
          <Input
            type="number"
            inputMode="numeric"
            placeholder={t('catalog.yearFrom')}
            aria-label={t('catalog.yearFrom')}
            value={filters.yearFrom ?? ''}
            onChange={(event) => update({ yearFrom: numberOrUndefined(event.target.value) })}
          />
          <span className={styles.dash}>—</span>
          <Input
            type="number"
            inputMode="numeric"
            placeholder={t('catalog.yearTo')}
            aria-label={t('catalog.yearTo')}
            value={filters.yearTo ?? ''}
            onChange={(event) => update({ yearTo: numberOrUndefined(event.target.value) })}
          />
        </div>
        {narrowed ? (
          <Button variant="ghost" size="sm" onClick={reset}>
            ↺ {t('catalog.resetFilters')}
          </Button>
        ) : null}
      </div>

      {itemsQuery.isError ? (
        <ErrorState
          detail={
            itemsQuery.error instanceof ApiError && itemsQuery.error.status === 0
              ? t('errors.network')
              : undefined
          }
          onRetry={() => void itemsQuery.refetch()}
        />
      ) : null}
      {itemsQuery.isPending ? (
        <div className={styles.grid}>
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} height={300} />
          ))}
        </div>
      ) : null}
      {page && page.items.length === 0 ? (
        <EmptyState
          icon="✓"
          title={narrowed ? t('catalog.emptyTitle') : t('missing.emptyTitle')}
          description={narrowed ? t('catalog.emptyText') : t('missing.emptyText')}
          actions={
            <Link to="/catalog">
              <Button variant="secondary">{t('common.backToCatalog')}</Button>
            </Link>
          }
        />
      ) : null}
      {page && page.items.length > 0 ? (
        <div className={styles.grid}>
          {page.items.map((item) => (
            <CoinCard
              key={item.id}
              item={item}
              action={
                <Link to={`/collection/new?catalogItemId=${item.id}`} state={{ from: backTo }}>
                  <Button size="sm" variant="secondary">
                    + {t('card.addPurchase')}
                  </Button>
                </Link>
              }
            />
          ))}
        </div>
      ) : null}
      <Pagination
        page={filters.page}
        pageCount={pageCount}
        onChange={(next) => update({ page: next })}
      />
    </div>
  );
}
