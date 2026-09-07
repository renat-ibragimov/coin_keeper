import { useQuery } from '@tanstack/react-query';
import { CircleDashed, Coins, PieChart, TrendingUp } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import type { BootstrapOut, BreakdownEntry, ExchangeRateOut } from '@/shared/api/types';
import {
  currencySymbol,
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedPercent,
  formatSignedUah,
  formatUah,
} from '@/shared/lib/format';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  ProgressRing,
  Skeleton,
  StatTile,
} from '@/shared/ui';

import { fetchBootstrap } from './api';
import { nearestToCompletion, valueDelta } from './finance';
import styles from './DashboardPage.module.css';

export function DashboardPage() {
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });

  if (query.isError) {
    return (
      <ErrorState
        detail={
          query.error instanceof ApiError && query.error.status === 0
            ? t('errors.network')
            : undefined
        }
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.isPending) return <DashboardSkeleton />;

  const data = query.data;

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t('dashboard.title')} subtitle={t('dashboard.subtitle')} />

      {data.dashboard.isEmpty ? (
        <Card>
          <EmptyState
            icon={<Coins strokeWidth={1.75} />}
            title={t('dashboard.emptyTitle')}
            description={t('dashboard.emptyText')}
            actions={
              <>
                <Link to="/catalog">
                  <Button>{t('dashboard.emptyCatalog')}</Button>
                </Link>
                <Link to="/collection/coins/new">
                  <Button variant="secondary">{t('card.addPurchase')}</Button>
                </Link>
              </>
            }
          />
        </Card>
      ) : (
        <DashboardBody data={data} />
      )}
    </div>
  );
}

function DashboardBody({ data }: { data: BootstrapOut }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const { dashboard, exchangeRates } = data;
  const delta = valueDelta(dashboard.totalSpendUah, dashboard.marketValueUah);
  const deltaTone = delta.diffUah > 0 ? 'success' : delta.diffUah < 0 ? 'danger' : 'neutral';
  const series = nearestToCompletion(dashboard.seriesBreakdown).slice(0, 6);

  return (
    <>
      <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
        <Link to="/collection/coins" className={styles.tileLink}>
          <StatTile
            icon={<Coins strokeWidth={1.75} />}
            label={t('dashboard.tileCoins')}
            value={formatNumber(dashboard.collectionItems, locale, 0)}
            hint={t('dashboard.tileCoinsHint', { count: dashboard.completedItems })}
          />
        </Link>
        <Link to="/collection/missing" className={styles.tileLink}>
          <StatTile
            icon={<CircleDashed strokeWidth={1.75} />}
            label={t('dashboard.tileMissing')}
            value={formatNumber(dashboard.missingItems, locale, 0)}
            hint={t('dashboard.tileMissingHint', { count: dashboard.catalogItems })}
          />
        </Link>
        <Link to="/collection/series" className={styles.tileLink}>
          <StatTile
            icon={<PieChart strokeWidth={1.75} />}
            label={t('dashboard.tileCompletion')}
            value={formatPercent(dashboard.completionPercent, locale, 1)}
            hint={t('dashboard.progress', {
              owned: dashboard.completedItems,
              count: dashboard.catalogItems,
            })}
          />
        </Link>
        <Link to="/collection/money" className={styles.tileLink}>
          <StatTile
            icon={<TrendingUp strokeWidth={1.75} />}
            label={t('dashboard.marketValue')}
            value={formatUah(dashboard.marketValueUah, locale)}
            hint={
              delta.percent !== null ? (
                <span className={styles[deltaTone]}>
                  {formatSignedUah(delta.diffUah, locale)}{' '}
                  <span className={styles.deltaPercent}>
                    ({formatSignedPercent(delta.percent, locale)})
                  </span>
                </span>
              ) : (
                formatSignedUah(delta.diffUah, locale)
              )
            }
          />
        </Link>
      </section>

      <div className={styles.columns}>
        <div className={styles.stack}>
          <Card className={styles.stackCardGrow}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>{t('dashboard.nearestTitle')}</h2>
              <Link to="/collection/series" className={styles.cardLink}>
                {t('dashboard.allSeries')} →
              </Link>
            </div>
            {series.length === 0 ? (
              <p className={styles.muted}>{t('dashboard.nearestEmpty')}</p>
            ) : (
              <ul className={styles.seriesList}>
                {series.map((entry) => (
                  <li key={entry.id} className={styles.seriesRow}>
                    <ProgressRing
                      value={entry.ratio}
                      size={46}
                      stroke={4}
                      aria-label={formatPercent(entry.ratio * 100, locale) ?? ''}
                    >
                      {formatPercent(entry.ratio * 100, locale)}
                    </ProgressRing>
                    <div className={styles.seriesBody}>
                      <Link
                        to={`/collection/series/${entry.id}`}
                        className={`${styles.seriesName} ${styles.seriesNameStretched}`}
                      >
                        {entry.name}
                      </Link>
                      <div className={styles.seriesMeta}>
                        {entry.country} ·{' '}
                        <span className="tabular">
                          {t('dashboard.progress', { owned: entry.owned, count: entry.count })}
                        </span>{' '}
                        · {t('dashboard.nearestMissing', { count: entry.missing })}
                      </div>
                      {/* Thumbnails of the missing coins need their own request
                          (docs/11-roadmap.md, part 3) — this row leaves room for them. */}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className={styles.stack}>
          <Card>
            <h2 className={styles.cardTitle}>{t('dashboard.financeTitle')}</h2>
            <dl className={styles.finance}>
              <FinanceRow
                label={t('dashboard.spentCoins')}
                value={formatUah(dashboard.coinSpendUah, locale)}
              />
              <FinanceRow
                label={t('dashboard.spentRelated')}
                value={formatUah(dashboard.relatedSpendUah, locale)}
              />
              <FinanceRow
                label={t('dashboard.spentTotal')}
                value={formatUah(dashboard.totalSpendUah, locale)}
                strong
              />
              <FinanceRow
                label={t('dashboard.marketValue')}
                value={formatUah(dashboard.marketValueUah, locale)}
                strong
              />
              <FinanceRow
                label={t('dashboard.delta')}
                hint={t('dashboard.deltaHint')}
                value={
                  <span className={styles[deltaTone]} data-testid="dashboard-delta">
                    {formatSignedUah(delta.diffUah, locale)}
                    {delta.percent !== null ? (
                      <span className={styles.deltaPercent}>
                        {' '}
                        {formatSignedPercent(delta.percent, locale)}
                      </span>
                    ) : null}
                  </span>
                }
              />
              <FinanceRow
                label={t('dashboard.missingBudget')}
                hint={
                  dashboard.unpricedMissingItems > 0
                    ? t('dashboard.unpriced', { count: dashboard.unpricedMissingItems })
                    : undefined
                }
                value={formatUah(dashboard.missingBudgetUah, locale)}
              />
            </dl>
          </Card>

          <Card className={styles.stackCardGrow}>
            <h2 className={styles.cardTitle}>{t('dashboard.ratesTitle')}</h2>
            <ExchangeRates rates={exchangeRates} />
          </Card>
        </div>
      </div>

      <Card>
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>{t('dashboard.countriesTitle')}</h2>
          <span className={styles.muted}>{t('dashboard.countriesHint')}</span>
        </div>
        <CountryBreakdown entries={dashboard.countryBreakdown} />
      </Card>
    </>
  );
}

function FinanceRow({
  label,
  hint,
  value,
  strong = false,
}: {
  label: string;
  hint?: string;
  value: ReactNode;
  strong?: boolean;
}) {
  return (
    <div className={[styles.financeRow, strong ? styles.financeStrong : ''].join(' ')}>
      <dt className={styles.financeLabel}>
        {label}
        {hint ? <span className={styles.financeHint}>{hint}</span> : null}
      </dt>
      <dd className={`${styles.financeValue} tabular`}>{value ?? '—'}</dd>
    </div>
  );
}

function CountryBreakdown({ entries }: { entries: BreakdownEntry[] }) {
  const { t, i18n } = useTranslation();
  if (entries.length === 0) return <p className={styles.muted}>{t('dashboard.countriesEmpty')}</p>;
  return (
    <ul className={styles.countryList}>
      {entries.map((entry) => {
        const ratio = entry.count > 0 ? entry.owned / entry.count : 0;
        return (
          <li key={entry.name} className={styles.countryRow}>
            <span className={styles.countryName}>{entry.name}</span>
            <span className={styles.countryBar} aria-hidden="true">
              <span className={styles.countryFill} style={{ width: `${ratio * 100}%` }} />
            </span>
            <span className={`${styles.countryCount} tabular`}>
              {t('dashboard.progress', { owned: entry.owned, count: entry.count })}
            </span>
            <span className={`${styles.countryPercent} tabular`}>
              {formatPercent(ratio * 100, i18n.language)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function ExchangeRates({ rates }: { rates: ExchangeRateOut[] }) {
  const { t, i18n } = useTranslation();
  const shown = rates.filter((rate) => rate.code === 'USD' || rate.code === 'EUR');
  const list = shown.length > 0 ? shown : rates;
  if (list.length === 0) return <p className={styles.muted}>{t('dashboard.rateMissing')}</p>;
  return (
    <ul className={styles.rates}>
      {list.map((rate) => {
        const value = formatNumber(rate.rate, i18n.language, 4);
        const date = formatDate(rate.effectiveDate, i18n.language);
        return (
          <li key={rate.code} className={styles.rateRow}>
            <span className={styles.rateCode}>
              1 {currencySymbol(rate.code)}
              <span className={styles.rateIso}> {rate.code}</span>
            </span>
            <span className={`${styles.rateValue} tabular`}>
              {value !== null ? `${value} ₴` : t('dashboard.rateMissing')}
            </span>
            <span className={styles.rateDate}>
              {date ? t('dashboard.ratesAsOf', { date }) : ''}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function DashboardSkeleton() {
  return (
    <div className={styles.page} aria-busy="true">
      <header className={styles.pageHeader}>
        <Skeleton width={260} height={40} />
        <Skeleton width={320} height={18} style={{ marginTop: 8 }} />
      </header>
      <div className={styles.tiles}>
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} height={96} />
        ))}
      </div>
      <div className={styles.columns}>
        <div className={styles.stack}>
          <Skeleton height={320} />
        </div>
        <div className={styles.stack}>
          <Skeleton height={240} />
          <Skeleton height={100} />
        </div>
      </div>
      <Skeleton height={100} />
    </div>
  );
}
