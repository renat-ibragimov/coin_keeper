import { useQuery } from '@tanstack/react-query';
import { Layers, SearchX } from 'lucide-react';
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

import { fetchCompletenessSummary } from './api';
import { groupByOptions, groupLabel, groupRouteValue, parseGroupBy } from './groupBy';
import type { CompletenessGroupBy } from './groupBy';
import { sortGroups } from './sort';
import type { CompletenessSort } from './sort';
import styles from './CompletenessListPage.module.css';

type CompletenessScope = 'mine' | 'all';

export function CompletenessListPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [params, setParams] = useSearchParams();
  const countryId = Number.parseInt(params.get('countryId') ?? '', 10) || undefined;
  const groupBy: CompletenessGroupBy = parseGroupBy(params.get('groupBy'));
  const sort: CompletenessSort = params.get('sort') === 'value' ? 'value' : 'completion';
  const scope: CompletenessScope = params.get('scope') === 'all' ? 'all' : 'mine';

  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const summaryQuery = useQuery({
    queryKey: ['completeness', 'summary', groupBy, countryId],
    queryFn: () => fetchCompletenessSummary(groupBy, countryId),
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

  const update = (changes: {
    countryId?: number;
    groupBy?: CompletenessGroupBy;
    sort?: CompletenessSort;
    scope?: CompletenessScope;
  }) => {
    const next = new URLSearchParams(params);
    if ('countryId' in changes) {
      if (changes.countryId) next.set('countryId', String(changes.countryId));
      else next.delete('countryId');
    }
    if (changes.groupBy) {
      if (changes.groupBy === 'series') next.delete('groupBy');
      else next.set('groupBy', changes.groupBy);
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
    () => (summaryQuery.data ? sortGroups(summaryQuery.data, sort) : []),
    [summaryQuery.data, sort],
  );
  const scopedRows = useMemo(
    () => (scope === 'mine' ? allRows.filter((row) => row.summary.owned > 0) : allRows),
    [allRows, scope],
  );
  const rows = useMemo(() => {
    const needle = debouncedSearch.trim().toLocaleLowerCase();
    if (!needle) return scopedRows;
    return scopedRows.filter((row) =>
      groupLabel(t, groupBy, row).toLocaleLowerCase().includes(needle),
    );
  }, [scopedRows, debouncedSearch, groupBy, t]);

  const noRowsAtAll = summaryQuery.data && allRows.length === 0;
  const noneStarted =
    summaryQuery.data && !noRowsAtAll && scope === 'mine' && scopedRows.length === 0;
  const nothingFound = summaryQuery.data && !noRowsAtAll && !noneStarted && rows.length === 0;

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        title={t('completeness.title')}
        subtitle={t('completeness.subtitle')}
      />

      {collectionEmpty ? (
        <EmptyState
          variant="card"
          icon={<Layers strokeWidth={1.75} />}
          title={t('completeness.emptyCollectionTitle')}
          description={t('completeness.emptyCollectionText')}
          actions={
            <>
              <Link to="/catalog">
                <Button>{t('common.backToCatalog')}</Button>
              </Link>
              <Link to="/collection/add">
                <Button variant="secondary">{t('card.addPurchase')}</Button>
              </Link>
            </>
          }
        />
      ) : (
        <>
          <div className={styles.toolbar}>
            <div className={styles.filters}>
              <div className={styles.search}>
                <Input
                  type="search"
                  placeholder={t('completeness.searchPlaceholder')}
                  aria-label={t('completeness.searchPlaceholder')}
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
              <Tabs<CompletenessGroupBy>
                aria-label={t('completeness.groupBySeries')}
                options={groupByOptions(t)}
                value={groupBy}
                onChange={(value) => update({ groupBy: value })}
              />
              <Tabs<CompletenessScope>
                options={[
                  { value: 'mine', label: t('completeness.scopeMine') },
                  { value: 'all', label: t('completeness.scopeAll') },
                ]}
                value={scope}
                onChange={(value) => update({ scope: value })}
              />
              <Tabs<CompletenessSort>
                aria-label={t('catalog.sort')}
                options={[
                  { value: 'completion', label: t('completeness.sortCompletion') },
                  { value: 'value', label: t('completeness.sortValue') },
                ]}
                value={sort}
                onChange={(value) => update({ sort: value })}
              />
            </div>
          </div>

          {summaryQuery.isError ? (
            <ErrorState
              detail={
                summaryQuery.error instanceof ApiError && summaryQuery.error.status === 0
                  ? t('errors.network')
                  : undefined
              }
              onRetry={() => void summaryQuery.refetch()}
            />
          ) : null}

          {summaryQuery.isPending ? (
            <div className={styles.list}>
              {Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} height={88} />
              ))}
            </div>
          ) : null}

          {noRowsAtAll ? (
            <EmptyState
              title={t('completeness.emptyTitle')}
              description={t('completeness.emptyText')}
            />
          ) : null}

          {noneStarted ? (
            <EmptyState
              icon={<Layers strokeWidth={1.75} />}
              title={t('completeness.emptyMineTitle')}
              description={t('completeness.emptyMineText')}
              actions={
                <Button variant="secondary" onClick={() => update({ scope: 'all' })}>
                  {t('completeness.showAll')}
                </Button>
              }
            />
          ) : null}

          {nothingFound ? (
            <EmptyState
              icon={<SearchX strokeWidth={1.75} />}
              title={t('catalog.emptyTitle')}
              description={t('catalog.emptyText')}
            />
          ) : null}

          {rows.length > 0 ? (
            <ul className={styles.list}>
              {rows.map((row) => (
                <li key={row.unassigned ? 'unassigned' : row.value} className={styles.row}>
                  <ProgressRing
                    value={row.summary.total ? row.summary.owned / row.summary.total : 0}
                    aria-label={formatPercent(row.summary.completionPercent, locale) ?? ''}
                  >
                    {formatPercent(row.summary.completionPercent, locale, 0)}
                  </ProgressRing>
                  <div className={styles.rowBody}>
                    <Link
                      to={`/collection/completeness/${groupBy}/${groupRouteValue(row)}`}
                      className={styles.name}
                    >
                      {groupLabel(t, groupBy, row)}
                    </Link>
                    <div className={styles.meta}>
                      {row.countryId ? (countryName.get(row.countryId) ?? '') : ''}
                      {row.startYear ? (
                        <span className="tabular">
                          {' '}
                          · {row.startYear}
                          {row.endYear ? `–${row.endYear}` : '–'}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <dl className={styles.stats}>
                    <div>
                      <dt>{t('completeness.collected')}</dt>
                      <dd className="tabular">
                        {t('dashboard.progress', {
                          owned: row.summary.owned,
                          count: row.summary.total,
                        })}
                      </dd>
                    </div>
                    <div>
                      <dt>{t('completeness.spent')}</dt>
                      <dd className="tabular">{formatUah(row.summary.purchaseTotalUah, locale)}</dd>
                    </div>
                    <div>
                      <dt>{t('completeness.value')}</dt>
                      <dd className="tabular">{formatUah(row.summary.currentValueUah, locale)}</dd>
                    </div>
                    <div>
                      <dt>{t('completeness.missing')}</dt>
                      <dd className="tabular">
                        {row.summary.missing}
                        {row.summary.unpricedMissing > 0 ? (
                          <span className={styles.muted}>
                            {' '}
                            · {t('dashboard.unpriced', { count: row.summary.unpricedMissing })}
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
