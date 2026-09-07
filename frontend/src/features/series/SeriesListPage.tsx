import { useQuery } from '@tanstack/react-query';
import { Layers } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { fetchCountries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import { formatPercent, formatUah } from '@/shared/lib/format';
import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  ProgressRing,
  Select,
  Skeleton,
  Tabs,
} from '@/shared/ui';

import { fetchSeriesProgress } from './api';
import { sortSeries } from './sort';
import type { SeriesSort } from './sort';
import styles from './SeriesListPage.module.css';

type SeriesScope = 'mine' | 'all';

export function SeriesListPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [params, setParams] = useSearchParams();
  const countryId = Number.parseInt(params.get('countryId') ?? '', 10) || undefined;
  const sort: SeriesSort = params.get('sort') === 'name' ? 'name' : 'completion';
  const scope: SeriesScope = params.get('scope') === 'all' ? 'all' : 'mine';

  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const progressQuery = useQuery({
    queryKey: ['series', 'progress', countryId],
    queryFn: () => fetchSeriesProgress(countryId),
  });
  const collectionEmpty = bootstrapQuery.data?.dashboard.isEmpty === true;
  const countryName = useMemo(() => {
    const map = new Map<number, string>();
    for (const country of countriesQuery.data ?? []) map.set(country.id, country.name);
    return map;
  }, [countriesQuery.data]);

  // The search box debounces before it narrows the (already fetched) rows.
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 400);
    return () => clearTimeout(timer);
  }, [search]);

  const update = (changes: { countryId?: number; sort?: SeriesSort; scope?: SeriesScope }) => {
    const next = new URLSearchParams(params);
    if ('countryId' in changes) {
      if (changes.countryId) next.set('countryId', String(changes.countryId));
      else next.delete('countryId');
    }
    if (changes.sort) {
      if (changes.sort === 'completion') next.delete('sort');
      else next.set('sort', changes.sort);
    }
    if (changes.scope) {
      if (changes.scope === 'mine') next.delete('scope');
      else next.set('scope', changes.scope);
    }
    setParams(next, { replace: true });
  };

  const allRows = useMemo(
    () => (progressQuery.data ? sortSeries(progressQuery.data, sort) : []),
    [progressQuery.data, sort],
  );
  const scopedRows = useMemo(
    () => (scope === 'mine' ? allRows.filter((row) => row.summary.owned > 0) : allRows),
    [allRows, scope],
  );
  const rows = useMemo(() => {
    const needle = debouncedSearch.trim().toLocaleLowerCase();
    if (!needle) return scopedRows;
    return scopedRows.filter(
      (row) =>
        row.series.name.toLocaleLowerCase().includes(needle) ||
        (countryName.get(row.series.countryId) ?? '').toLocaleLowerCase().includes(needle),
    );
  }, [scopedRows, debouncedSearch, countryName]);

  const noSeriesAtAll = progressQuery.data && allRows.length === 0;
  const noneStarted =
    progressQuery.data && !noSeriesAtAll && scope === 'mine' && scopedRows.length === 0;
  const nothingFound = progressQuery.data && !noSeriesAtAll && !noneStarted && rows.length === 0;

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t('series.title')} subtitle={t('series.subtitle')} />

      {collectionEmpty ? (
        <EmptyState
          title={t('series.emptyCollectionTitle')}
          description={t('series.emptyCollectionText')}
          actions={
            <Link to="/catalog">
              <Button>{t('common.backToCatalog')}</Button>
            </Link>
          }
        />
      ) : (
        <>
          <div className={styles.toolbar}>
            <div className={styles.filters}>
              <div className={styles.search}>
                <Input
                  type="search"
                  placeholder={t('series.searchPlaceholder')}
                  aria-label={t('series.searchPlaceholder')}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <Select
                aria-label={t('catalog.country')}
                value={countryId ?? ''}
                onChange={(event) => update({ countryId: Number(event.target.value) || undefined })}
              >
                <option value="">{t('catalog.allCountries')}</option>
                {(countriesQuery.data ?? []).map((country) => (
                  <option key={country.id} value={country.id}>
                    {country.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className={styles.controls}>
              <Tabs<SeriesScope>
                options={[
                  { value: 'mine', label: t('series.scopeMine') },
                  { value: 'all', label: t('series.scopeAll') },
                ]}
                value={scope}
                onChange={(value) => update({ scope: value })}
              />
              <Tabs<SeriesSort>
                aria-label={t('catalog.sort')}
                options={[
                  { value: 'completion', label: t('series.sortCompletion') },
                  { value: 'name', label: t('series.sortName') },
                ]}
                value={sort}
                onChange={(value) => update({ sort: value })}
              />
            </div>
          </div>

          {progressQuery.isError ? (
            <ErrorState
              detail={
                progressQuery.error instanceof ApiError && progressQuery.error.status === 0
                  ? t('errors.network')
                  : undefined
              }
              onRetry={() => void progressQuery.refetch()}
            />
          ) : null}

          {progressQuery.isPending ? (
            <div className={styles.list}>
              {Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} height={88} />
              ))}
            </div>
          ) : null}

          {noSeriesAtAll ? (
            <EmptyState title={t('series.emptyTitle')} description={t('series.emptyText')} />
          ) : null}

          {noneStarted ? (
            <EmptyState
              icon={<Layers strokeWidth={1.75} />}
              title={t('series.emptyMineTitle')}
              description={t('series.emptyMineText')}
              actions={
                <Button variant="secondary" onClick={() => update({ scope: 'all' })}>
                  {t('series.showAllSeries')}
                </Button>
              }
            />
          ) : null}

          {nothingFound ? (
            <EmptyState title={t('catalog.emptyTitle')} description={t('catalog.emptyText')} />
          ) : null}

          {rows.length > 0 ? (
            <ul className={styles.list}>
              {rows.map(({ series, summary }) => (
                <li key={series.id} className={styles.row}>
                  <ProgressRing
                    value={summary.total ? summary.owned / summary.total : 0}
                    aria-label={formatPercent(summary.completionPercent, locale) ?? ''}
                  >
                    {formatPercent(summary.completionPercent, locale, 0)}
                  </ProgressRing>
                  <div className={styles.rowBody}>
                    <Link to={`/collection/series/${series.id}`} className={styles.name}>
                      {series.name}
                    </Link>
                    <div className={styles.meta}>
                      {countryName.get(series.countryId) ?? ''}
                      {series.startYear ? (
                        <span className="tabular">
                          {' '}
                          · {series.startYear}
                          {series.endYear ? `–${series.endYear}` : '–'}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <dl className={styles.stats}>
                    <div>
                      <dt>{t('series.collected')}</dt>
                      <dd className="tabular">
                        {t('dashboard.progress', { owned: summary.owned, count: summary.total })}
                      </dd>
                    </div>
                    <div>
                      <dt>{t('series.spent')}</dt>
                      <dd className="tabular">{formatUah(summary.purchaseTotalUah, locale)}</dd>
                    </div>
                    <div>
                      <dt>{t('series.value')}</dt>
                      <dd className="tabular">{formatUah(summary.currentValueUah, locale)}</dd>
                    </div>
                    <div>
                      <dt>{t('series.missing')}</dt>
                      <dd className="tabular">
                        {summary.missing}
                        {summary.unpricedMissing > 0 ? (
                          <span className={styles.muted}>
                            {' '}
                            · {t('dashboard.unpriced', { count: summary.unpricedMissing })}
                          </span>
                        ) : null}
                      </dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
}
