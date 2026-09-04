import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { fetchCountries } from '@/features/catalog/api';
import { ApiError } from '@/shared/api/client';
import { formatPercent, formatUah } from '@/shared/lib/format';
import {
  EmptyState,
  ErrorState,
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

export function SeriesListPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [params, setParams] = useSearchParams();
  const countryId = Number.parseInt(params.get('countryId') ?? '', 10) || undefined;
  const sort: SeriesSort = params.get('sort') === 'name' ? 'name' : 'completion';

  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const progressQuery = useQuery({
    queryKey: ['series', 'progress', countryId],
    queryFn: () => fetchSeriesProgress(countryId),
  });
  const countryName = useMemo(() => {
    const map = new Map<number, string>();
    for (const country of countriesQuery.data ?? []) map.set(country.id, country.name);
    return map;
  }, [countriesQuery.data]);

  const rows = useMemo(
    () => (progressQuery.data ? sortSeries(progressQuery.data, sort) : []),
    [progressQuery.data, sort],
  );

  const update = (changes: { countryId?: number; sort?: SeriesSort }) => {
    const next = new URLSearchParams(params);
    if ('countryId' in changes) {
      if (changes.countryId) next.set('countryId', String(changes.countryId));
      else next.delete('countryId');
    }
    if (changes.sort) {
      if (changes.sort === 'completion') next.delete('sort');
      else next.set('sort', changes.sort);
    }
    setParams(next, { replace: true });
  };

  return (
    <div className={styles.page}>
      <PageHeader title={t('series.title')} subtitle={t('series.subtitle')} />

      <div className={styles.toolbar}>
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

      {progressQuery.data && rows.length === 0 ? (
        <EmptyState title={t('series.emptyTitle')} description={t('series.emptyText')} />
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
                <Link to={`/series/${series.id}`} className={styles.name}>
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
    </div>
  );
}
