import { CalendarDays, Coins, Receipt, Wallet } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ExpensesByMonthChart } from '@/features/expenses/ExpensesByMonthChart';
import { ExpensesPeriodPicker } from '@/features/expenses/ExpensesPeriodPicker';
import { presetRange } from '@/features/expenses/period';
import type { ExpensesPeriodPreset } from '@/features/expenses/period';
import { formatDate, formatMonthYear, formatUah } from '@/shared/lib/format';
import { useChartPalette } from '@/shared/theme/useChartPalette';

import type { LandingCopy } from './copy';
import { expenseDemoChart, expenseDemoRows, expenseDemoToday } from './expenseDemoData';
import styles from './LandingPage.module.css';

export function ExpensesDemo({ c, en }: { c: LandingCopy; en: boolean }) {
  const { t } = useTranslation();
  const locale = en ? 'en' : 'uk';
  const palette = useChartPalette();
  const [preset, setPreset] = useState<ExpensesPeriodPreset | null>('6m');
  const [range, setRange] = useState(() => presetRange('6m', expenseDemoToday));
  const [category, setCategory] = useState('');
  const [page, setPage] = useState(0);
  const invalidRange = Boolean(range.dateFrom && range.dateTo && range.dateFrom > range.dateTo);
  const chart = expenseDemoChart(range.dateFrom, range.dateTo);
  // Like ExpensesPage: period scopes the chart, category scopes the journal;
  // neither changes the all-time/current-month summary tiles.
  const sum = (rows: typeof expenseDemoRows) => rows.reduce((total, row) => total + row.amount, 0);
  const coins = expenseDemoRows.filter((row) => row.category === 'coin_purchase');
  const related = expenseDemoRows.filter((row) => row.category !== 'coin_purchase');
  const snapshotMonth = presetRange('1m', expenseDemoToday).dateTo.slice(0, 7);
  const stats = [
    {
      key: 'tileTotal',
      amount: sum(expenseDemoRows),
      hint: t('expenses.count', { count: expenseDemoRows.length }),
      icon: Wallet,
    },
    {
      key: 'tileCoins',
      amount: sum(coins),
      hint: t('expenses.count', { count: coins.length }),
      icon: Coins,
    },
    {
      key: 'tileRelated',
      amount: sum(related),
      hint: t('expenses.count', { count: related.length }),
      icon: Receipt,
    },
    {
      key: 'tileThisMonth',
      amount: sum(expenseDemoRows.filter((row) => row.date.startsWith(snapshotMonth))),
      hint: formatMonthYear(`${snapshotMonth}-01`, locale),
      icon: CalendarDays,
    },
  ];
  const journal = expenseDemoRows.filter((row) => !category || row.category === category);
  const pageSize = 4;
  const visibleRows = journal.slice(page * pageSize, (page + 1) * pageSize);

  return (
    <div className={`${styles.demoFrame} ${styles.financeDemo}`}>
      <div className={styles.demoHeader}>
        <h3>
          <Wallet size={18} />
          {t('expenses.title')}
        </h3>
      </div>
      <div className={styles.collectionMetrics}>
        {stats.map(({ key, amount, hint, icon: Icon }) => (
          <div key={key}>
            <Icon size={15} />
            <div>
              <span>{t(`expenses.${key}`)}</span>
              <strong>{formatUah(amount, locale)}</strong>
              <small>{hint}</small>
            </div>
          </div>
        ))}
      </div>
      <div className={styles.financePeriod}>
        <ExpensesPeriodPicker
          preset={preset}
          dateFrom={range.dateFrom}
          dateTo={range.dateTo}
          invalidRange={invalidRange}
          onPreset={(next) => {
            setPreset(next);
            setRange(presetRange(next, expenseDemoToday));
          }}
          onCustomRange={(dateFrom, dateTo) => {
            setPreset(null);
            setRange({ dateFrom, dateTo });
          }}
        />
      </div>
      <div className={styles.financeChart}>
        <h4>{t('expenses.chartByMonthTitle')}</h4>
        {!invalidRange && chart.byCategory.length ? (
          <ExpensesByMonthChart
            data={chart.byPeriod}
            granularity={chart.granularity}
            locale={locale}
            palette={palette}
          />
        ) : (
          <p className={styles.financeChartEmpty}>
            {invalidRange ? t('expenses.periodInvalid') : t('expenses.chartPeriodEmpty')}
          </p>
        )}
      </div>
      <div className={styles.financeCategories} aria-label={t('expenses.category')}>
        {['', 'coin_purchase', 'delivery'].map((value) => (
          <button
            type="button"
            key={value}
            aria-pressed={category === value}
            onClick={() => {
              setCategory(value);
              setPage(0);
            }}
          >
            {value ? t(`expenses.categories.${value}`) : t('expenses.allCategories')}
            {value && <span>{expenseDemoRows.filter((row) => row.category === value).length}</span>}
          </button>
        ))}
      </div>
      <div className={styles.financeJournal}>
        <table>
          <thead>
            <tr>
              {['date', 'category', 'description', 'amountHeader'].map((key) => (
                <th key={key}>{t(`expenses.${key}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={`${row.date}-${row.category}`}>
                <td>{formatDate(row.date, locale)}</td>
                <td>
                  <span
                    className={
                      row.category === 'coin_purchase' ? styles.purchaseBadge : styles.expenseBadge
                    }
                  >
                    {t(`expenses.categories.${row.category}`)}
                  </span>
                </td>
                <td>{c.demoNames[row.coin]}</td>
                <td>{formatUah(row.amount, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={styles.financePagination}>
        <span>{t('pagination.shown', { shown: visibleRows.length, total: journal.length })}</span>
        <div>
          <button
            type="button"
            disabled={page === 0}
            aria-label={t('pagination.previous')}
            onClick={() => setPage(page - 1)}
          >
            ←
          </button>
          <button
            type="button"
            disabled={(page + 1) * pageSize >= journal.length}
            aria-label={t('pagination.next')}
            onClick={() => setPage(page + 1)}
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
}
