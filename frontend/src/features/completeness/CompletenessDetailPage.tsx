import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { fetchCountries, fetchSeries, PAGE_SIZE } from '@/features/catalog/api';
import { CoinCard } from '@/features/catalog/CoinCard';
import { ApiError } from '@/shared/api/client';
import type { MetalKind } from '@/shared/api/types';
import { formatPercent, formatUah } from '@/shared/lib/format';
import {
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
  StatTile,
  Tabs,
} from '@/shared/ui';

import { fetchCompletenessGroup, fetchCompletenessItems } from './api';
import type { GroupSelector } from './api';
import { parseCountryId, parseMetalKind } from './filters';
import { groupLabel, parseGroupBy } from './groupBy';
import { MetalKindSelect } from './MetalKindSelect';
import styles from './CompletenessDetailPage.module.css';

// Whether the item grid narrows to what's collected -- the detail screen's
// own filter, independent of the list's "Мої"/"Усі" scope tab (which decides
// which whole GROUPS the list shows, meaningless once one group is open).
type ItemsScope = 'mine' | 'all';

export function CompletenessDetailPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const { groupBy: groupByParam, value: valueParam } = useParams();
  const [params, setParams] = useSearchParams();
  const groupBy = parseGroupBy(groupByParam);
  const unassigned = valueParam === 'none';
  const numericValue = Number.parseInt(valueParam ?? '', 10);
  const valid = unassigned || (Number.isFinite(numericValue) && numericValue > 0);
  const selector: GroupSelector | undefined = !valid
    ? undefined
    : unassigned
      ? { unassigned: true }
      : { value: numericValue };
  const [page, setPage] = useState(1);

  const countryId = parseCountryId(params.get('countryId'));
  const metalKind = parseMetalKind(params.get('metalKind'));
  const itemsScope: ItemsScope = params.get('owned') === 'true' ? 'mine' : 'all';
  const owned = itemsScope === 'mine' ? true : undefined;

  const update = (changes: {
    countryId?: number;
    metalKind?: MetalKind | null;
    itemsScope?: ItemsScope;
  }) => {
    const next = new URLSearchParams(params);
    if ('countryId' in changes) {
      if (changes.countryId) next.set('countryId', String(changes.countryId));
      else next.delete('countryId');
    }
    if ('metalKind' in changes) {
      if (changes.metalKind) next.set('metalKind', changes.metalKind);
      else next.delete('metalKind');
    }
    if (changes.itemsScope) {
      if (changes.itemsScope === 'all') next.delete('owned');
      else next.set('owned', 'true');
    }
    setParams(next, { replace: true });
    setPage(1);
  };

  // Every series' id, for `CoinCard`'s own series link -- a group of any
  // dimension (year, denomination, material) can mix coins from several
  // series, so this isn't limited to `groupBy === 'series'`.
  const seriesQuery = useQuery({
    queryKey: ['series', 'list', undefined],
    queryFn: () => fetchSeries(),
  });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const groupQuery = useQuery({
    queryKey: ['completeness', 'group', groupBy, valueParam, countryId, metalKind],
    queryFn: () => fetchCompletenessGroup(groupBy, selector as GroupSelector, countryId, metalKind),
    enabled: selector !== undefined,
  });
  const itemsQuery = useQuery({
    queryKey: ['completeness', 'items', groupBy, valueParam, countryId, metalKind, owned, page],
    queryFn: () =>
      fetchCompletenessItems(
        groupBy,
        selector as GroupSelector,
        countryId,
        metalKind,
        owned,
        page,
        PAGE_SIZE,
      ),
    enabled: selector !== undefined,
    placeholderData: keepPreviousData,
  });

  const seriesIdByName = useMemo(
    () => Object.fromEntries((seriesQuery.data ?? []).map((row) => [row.name, row.id])),
    [seriesQuery.data],
  );
  const group = groupQuery.data;
  const country = countriesQuery.data?.find((row) => row.id === group?.countryId);
  // Neither "confirmed" nor "not confirmed" is the right guess while this is
  // still loading -- rendering nothing until it's known avoids a flash from
  // one to the other (docs/business-rules.md, BR-13a).
  const confirmedKnown = countriesQuery.data !== undefined && group !== undefined;
  const catalogConfirmed = country?.catalogConfirmed === true;
  const notFound =
    !valid || (groupQuery.error instanceof ApiError && groupQuery.error.status === 404);

  if (notFound) {
    return (
      <ErrorState
        title={t('completeness.notFound')}
        actions={
          <Link to="/collection/completeness">
            <Button variant="secondary">{t('nav.completeness')}</Button>
          </Link>
        }
      />
    );
  }

  const items = itemsQuery.data;
  const pageCount = Math.max(1, Math.ceil((items?.total ?? 0) / PAGE_SIZE));
  const search = params.toString();
  const backTo = `/collection/completeness/${groupBy}/${valueParam ?? ''}${search ? `?${search}` : ''}`;

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        title={group ? groupLabel(t, groupBy, group) : <Skeleton width={280} height={36} />}
        subtitle={
          group
            ? [
                country?.name,
                group.startYear
                  ? `${group.startYear}${group.endYear ? `–${group.endYear}` : '–'}`
                  : null,
              ]
                .filter(Boolean)
                .join(' · ')
            : undefined
        }
        actions={
          groupBy === 'series' && group && confirmedKnown && catalogConfirmed ? (
            <Link to={`/catalog?seriesId=${group.value}`}>
              <Button variant="secondary">{t('completeness.openInCatalog')}</Button>
            </Link>
          ) : undefined
        }
      />

      {groupBy === 'series' && confirmedKnown && !catalogConfirmed ? (
        <p className={styles.notConfirmedNotice}>{t('completeness.notInCatalogNotice')}</p>
      ) : null}

      {groupBy === 'series' && group?.description ? (
        <p className={styles.description}>{group.description}</p>
      ) : null}

      <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
        {group ? (
          <>
            <StatTile
              label={t('completeness.collected')}
              value={t('dashboard.progress', {
                owned: group.summary.owned,
                count: group.summary.total,
              })}
              hint={formatPercent(group.summary.completionPercent, locale, 1)}
            />
            <StatTile
              label={t('completeness.spent')}
              value={formatUah(group.summary.purchaseTotalUah, locale)}
            />
            <StatTile
              label={t('completeness.value')}
              value={formatUah(group.summary.currentValueUah, locale)}
            />
            <StatTile
              label={t('completeness.missing')}
              value={group.summary.missing}
              hint={
                group.summary.unpricedMissing > 0
                  ? t('dashboard.unpriced', { count: group.summary.unpricedMissing })
                  : undefined
              }
            />
          </>
        ) : (
          Array.from({ length: 4 }, (_, index) => <Skeleton key={index} height={96} />)
        )}
      </section>

      <div className={styles.toolbar}>
        <Select
          aria-label={t('catalog.country')}
          value={countryId ?? ''}
          onChange={(event) => update({ countryId: Number(event.target.value) || undefined })}
        >
          <option value="">{t('catalog.allCountries')}</option>
          {(countriesQuery.data ?? []).map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </Select>
        <MetalKindSelect value={metalKind} onChange={(value) => update({ metalKind: value })} />
        <Tabs<ItemsScope>
          options={[
            { value: 'mine', label: t('completeness.scopeMine') },
            { value: 'all', label: t('completeness.scopeAll') },
          ]}
          value={itemsScope}
          onChange={(value) => update({ itemsScope: value })}
        />
      </div>

      {itemsQuery.isError ? <ErrorState onRetry={() => void itemsQuery.refetch()} /> : null}
      {itemsQuery.isPending ? (
        <div className={styles.grid}>
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton key={index} height={300} />
          ))}
        </div>
      ) : null}
      {items && items.items.length === 0 ? (
        <EmptyState
          title={t('completeness.noItemsTitle')}
          description={t('completeness.noItemsText')}
        />
      ) : null}
      {items && items.items.length > 0 ? (
        <div className={styles.grid}>
          {items.items.map((item) => (
            <CoinCard key={item.id} item={item} backTo={backTo} seriesIdByName={seriesIdByName} />
          ))}
        </div>
      ) : null}
      <Pagination page={page} pageCount={pageCount} onChange={setPage} />
    </div>
  );
}
