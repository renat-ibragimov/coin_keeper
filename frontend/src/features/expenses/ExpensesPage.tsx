import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarDays, Coins, Receipt, Wallet } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import type { ExpenseCategory, ExpenseOut } from '@/shared/api/types';
import { formatDate, formatMoney, formatSignedUah, formatUah } from '@/shared/lib/format';
import { useChartPalette } from '@/shared/theme/useChartPalette';
import type { SortOrder } from '@/shared/ui';
import {
  Badge,
  Button,
  Card,
  cellAlign,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
  Pagination,
  Skeleton,
  SortHeader,
  StatTile,
  useToast,
} from '@/shared/ui';

import {
  ALL_CATEGORIES,
  createExpense,
  deleteExpense,
  EXPENSE_SORTS,
  fetchExpenses,
  fetchExpensesSummary,
  PAGE_SIZE,
  updateExpense,
} from './api';
import type { ExpenseSort } from './api';
import { ExpensesByCategoryChart } from './ExpensesByCategoryChart';
import { ExpensesByMonthChart } from './ExpensesByMonthChart';
import { ExpenseForm } from './ExpenseForm';
import type { ExpenseValues } from './ExpenseForm';
import styles from './ExpensesPage.module.css';

const DEPENDENT_KEYS = ['expenses', 'bootstrap'];

// Widths of their own, so the columns stay put from page to page (the same
// rule as the other two tables, docs/08-ui-map.md).
const SORTABLE_COLUMNS: { key: string; sort: ExpenseSort; className: string | undefined }[] = [
  { key: 'expenses.date', sort: 'date', className: styles.dateColumn },
  { key: 'expenses.category', sort: 'category', className: styles.categoryColumn },
  { key: 'expenses.description', sort: 'description', className: undefined },
  { key: 'expenses.vendor', sort: 'vendor', className: styles.vendorColumn },
  { key: 'expenses.amountHeader', sort: 'amount', className: styles.moneyColumn },
];

type Editor = { mode: 'closed' } | { mode: 'create' } | { mode: 'edit'; expense: ExpenseOut };

export function ExpensesPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const queryClient = useQueryClient();

  const categoryParam = params.get('category');
  const category = ALL_CATEGORIES.includes(categoryParam as ExpenseCategory)
    ? (categoryParam as ExpenseCategory)
    : undefined;
  const page = Math.max(1, Number.parseInt(params.get('page') ?? '1', 10) || 1);
  const sortParam = params.get('sort');
  const sort = EXPENSE_SORTS.includes(sortParam as ExpenseSort)
    ? (sortParam as ExpenseSort)
    : 'date';
  const order = params.get('order') === 'asc' ? 'asc' : 'desc';
  const [editor, setEditor] = useState<Editor>({ mode: 'closed' });
  const [deleting, setDeleting] = useState<ExpenseOut | null>(null);

  const listQuery = useQuery({
    queryKey: ['expenses', 'list', category, page, sort, order],
    queryFn: () => fetchExpenses({ category, page, sort, order }),
    placeholderData: keepPreviousData,
  });
  const summaryQuery = useQuery({
    queryKey: ['expenses', 'summary'],
    queryFn: fetchExpensesSummary,
  });
  const currenciesQuery = useQuery({ queryKey: ['currencies'], queryFn: fetchCurrencies });
  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const collectionEmpty = bootstrapQuery.data?.dashboard.isEmpty === true;

  const invalidate = () =>
    Promise.all(DEPENDENT_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: [key] })));

  const saveMutation = useMutation({
    mutationFn: (values: ExpenseValues) =>
      editor.mode === 'edit' ? updateExpense(editor.expense.id, values) : createExpense(values),
    onSuccess: async () => {
      await invalidate();
      toast.show(editor.mode === 'edit' ? t('expenses.updated') : t('expenses.created'));
      setEditor({ mode: 'closed' });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteExpense(id),
    onSuccess: async () => {
      await invalidate();
      toast.show(t('expenses.deleted'));
      setDeleting(null);
    },
    onError: () => toast.show(t('errors.generic'), 'error'),
  });

  const setFilter = (changes: {
    category?: ExpenseCategory;
    page?: number;
    sort?: ExpenseSort;
    order?: SortOrder;
  }) => {
    const next = new URLSearchParams(params);
    if ('category' in changes) {
      if (changes.category) next.set('category', changes.category);
      else next.delete('category');
      next.delete('page');
    }
    if (changes.sort) {
      // The listing's own default stays out of the address, same rule as the
      // catalogue's filters: a plain link is a plain link.
      if (changes.sort === 'date') next.delete('sort');
      else next.set('sort', changes.sort);
      if (changes.order === 'asc') next.set('order', 'asc');
      else next.delete('order');
      next.delete('page');
    }
    if (changes.page && changes.page > 1) next.set('page', String(changes.page));
    else if ('page' in changes) next.delete('page');
    setParams(next, { replace: true });
  };

  const summary = summaryQuery.data;
  const coins = summary?.categories.find((row) => row.category === 'coin_purchase');
  const relatedUah = summary
    ? summary.categories
        .filter((row) => row.category !== 'coin_purchase')
        .reduce((sum, row) => sum + Number(row.totalUah), 0)
    : null;
  const relatedCount = summary
    ? summary.categories
        .filter((row) => row.category !== 'coin_purchase')
        .reduce((sum, row) => sum + row.count, 0)
    : 0;
  const totalCount = summary ? summary.categories.reduce((sum, row) => sum + row.count, 0) : 0;
  const list = listQuery.data;
  const pageCount = Math.max(1, Math.ceil((list?.total ?? 0) / PAGE_SIZE));
  const palette = useChartPalette();

  const thisMonth = summary ? Number(summary.thisMonthUah) : null;
  const prevMonth = summary ? Number(summary.prevMonthUah) : null;
  const thisMonthHint =
    thisMonth !== null && prevMonth !== null
      ? prevMonth === 0 && thisMonth > 0
        ? t('expenses.thisMonthHintNoPrev')
        : t('expenses.thisMonthHint', {
            delta: formatSignedUah(thisMonth - prevMonth, locale),
          })
      : null;

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        title={t('expenses.title')}
        subtitle={t('expenses.subtitle')}
        actions={
          collectionEmpty ? undefined : (
            <Button onClick={() => setEditor({ mode: 'create' })}>+ {t('expenses.add')}</Button>
          )
        }
      />

      {collectionEmpty ? (
        <EmptyState
          variant="card"
          icon={<Wallet strokeWidth={1.75} />}
          title={t('expenses.emptyCollectionTitle')}
          description={t('expenses.emptyCollectionText')}
          actions={
            <>
              <Link to="/catalog">
                <Button>{t('common.backToCatalog')}</Button>
              </Link>
              <Link to="/collection/coins/new">
                <Button variant="secondary">{t('card.addPurchase')}</Button>
              </Link>
            </>
          }
          note={<Link to="/import">{t('catalog.importUcoin')}</Link>}
        />
      ) : (
        <>
          <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
            {summary ? (
              <>
                <StatTile
                  icon={<Wallet strokeWidth={1.75} />}
                  label={t('expenses.tileTotal')}
                  value={formatUah(summary.totalUah, locale)}
                  hint={t('expenses.count', { count: totalCount })}
                />
                <StatTile
                  icon={<Coins strokeWidth={1.75} />}
                  label={t('expenses.tileCoins')}
                  value={formatUah(coins?.totalUah ?? '0', locale)}
                  hint={t('expenses.count', { count: coins?.count ?? 0 })}
                />
                <StatTile
                  icon={<Receipt strokeWidth={1.75} />}
                  label={t('expenses.tileRelated')}
                  value={formatUah(relatedUah, locale)}
                  hint={t('expenses.count', { count: relatedCount })}
                />
                <StatTile
                  icon={<CalendarDays strokeWidth={1.75} />}
                  label={t('expenses.tileThisMonth')}
                  value={formatUah(summary.thisMonthUah, locale)}
                  hint={thisMonthHint}
                />
              </>
            ) : (
              Array.from({ length: 4 }, (_, index) => <Skeleton key={index} height={96} />)
            )}
          </section>

          {summary && summary.categories.length > 0 ? (
            <div className={styles.charts}>
              <Card variant="panel" aria-label={t('expenses.chartByMonthTitle')}>
                <h3 className={styles.chartTitle}>{t('expenses.chartByMonthTitle')}</h3>
                <ExpensesByMonthChart data={summary.byMonth} locale={locale} palette={palette} />
              </Card>
              <Card variant="panel" aria-label={t('expenses.chartByCategoryTitle')}>
                <h3 className={styles.chartTitle}>{t('expenses.chartByCategoryTitle')}</h3>
                <ExpensesByCategoryChart
                  data={summary.byCategory}
                  locale={locale}
                  palette={palette}
                />
              </Card>
            </div>
          ) : null}

          {summary && summary.categories.length > 0 ? (
            <div className={styles.chips} role="group" aria-label={t('expenses.category')}>
              <button
                type="button"
                className={[styles.chip, category === undefined ? styles.chipActive : ''].join(' ')}
                onClick={() => setFilter({ category: undefined })}
                aria-pressed={category === undefined}
              >
                {t('expenses.allCategories')}
              </button>
              {summary.categories.map((row) => (
                <button
                  key={row.category}
                  type="button"
                  className={[styles.chip, category === row.category ? styles.chipActive : ''].join(
                    ' ',
                  )}
                  onClick={() => setFilter({ category: row.category })}
                  aria-pressed={category === row.category}
                >
                  {t(`expenses.categories.${row.category}`)}
                  <span className={`${styles.chipCount} tabular`}>{row.count}</span>
                </button>
              ))}
            </div>
          ) : null}

          {listQuery.isError ? (
            <ErrorState
              detail={
                listQuery.error instanceof ApiError && listQuery.error.status === 0
                  ? t('errors.network')
                  : undefined
              }
              onRetry={() => void listQuery.refetch()}
            />
          ) : null}
          {listQuery.isPending ? <Skeleton height={280} /> : null}
          {list && list.items.length === 0 ? (
            <EmptyState
              icon={<Wallet strokeWidth={1.75} />}
              title={t('expenses.emptyTitle')}
              description={t('expenses.emptyText')}
              actions={
                <Button variant="secondary" onClick={() => setEditor({ mode: 'create' })}>
                  + {t('expenses.add')}
                </Button>
              }
            />
          ) : null}
          {list && list.items.length > 0 ? (
            <DataTable minWidth={860}>
              <thead>
                <tr>
                  {SORTABLE_COLUMNS.map((column) => (
                    <SortHeader
                      key={column.key}
                      label={t(column.key)}
                      field={column.sort}
                      sort={sort}
                      order={order}
                      onSort={(nextSort, nextOrder) =>
                        setFilter({ sort: nextSort, order: nextOrder })
                      }
                      className={column.className}
                    />
                  ))}
                  {/* Reserved for the amount in dollars at the National Bank's
                      rate of the day, so the spending can be read in a currency
                      that does not move under your feet. The value comes in a
                      later step (docs/BACKLOG.md), and nothing sorts by a column
                      that carries none yet. */}
                  <th className={styles.usdColumn}>{t('expenses.amountUsdHeader')}</th>
                  <th className={styles.actionsColumn}>{t('catalog.tableActions')}</th>
                </tr>
              </thead>
              <tbody>
                {list.items.map((expense) => {
                  const fromPurchase = expense.category === 'coin_purchase';
                  return (
                    <tr key={expense.id}>
                      <td className={`${cellAlign.center} tabular`}>
                        {formatDate(expense.expenseDate, locale)}
                      </td>
                      <td className={cellAlign.center}>
                        <Badge tone={fromPurchase ? 'accent' : 'neutral'}>
                          {t(`expenses.categories.${expense.category}`)}
                        </Badge>
                      </td>
                      <td>
                        {fromPurchase && expense.catalogItemId ? (
                          <Link to={`/catalog/${expense.catalogItemId}`}>
                            {expense.coinTitle || t('expenses.fromPurchase')}
                          </Link>
                        ) : (
                          expense.description || '—'
                        )}
                      </td>
                      <td className={`${cellAlign.center} ${styles.secondary}`}>
                        {expense.vendor || '—'}
                      </td>
                      <td className={`${cellAlign.center} tabular`}>
                        {formatMoney(expense.amount, expense.currencyCode, locale)}
                      </td>
                      {/* In dollars at the rate of the day: the column is in
                          place, the value comes from the API later. */}
                      <td className={`${cellAlign.center} ${styles.muted} tabular`}>—</td>
                      <td className={styles.actions}>
                        {/* A purchase's expense is maintained by the purchase
                              itself, so there is nothing to press here — an
                              empty cell rather than a dash that reads as a
                              missing value (owner, 2026-09-09). */}
                        {fromPurchase ? null : (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setEditor({ mode: 'edit', expense })}
                            >
                              {t('common.edit')}
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setDeleting(expense)}>
                              {t('common.delete')}
                            </Button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </DataTable>
          ) : null}
          <Pagination
            page={page}
            pageCount={pageCount}
            onChange={(next) => setFilter({ page: next })}
          />
        </>
      )}

      <Modal
        open={editor.mode !== 'closed'}
        onClose={() => setEditor({ mode: 'closed' })}
        title={editor.mode === 'edit' ? t('expenses.editTitle') : t('expenses.addTitle')}
      >
        {editor.mode !== 'closed' ? (
          <ExpenseForm
            key={editor.mode === 'edit' ? editor.expense.id : 'new'}
            initial={editor.mode === 'edit' ? editor.expense : undefined}
            currencies={currenciesQuery.data ?? []}
            busy={saveMutation.isPending}
            submitError={saveMutation.error}
            onSubmit={(values) => saveMutation.mutate(values)}
            onCancel={() => setEditor({ mode: 'closed' })}
          />
        ) : null}
      </Modal>

      <ConfirmDialog
        open={deleting !== null}
        title={t('expenses.deleteTitle')}
        confirmLabel={t('common.delete')}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        busy={deleteMutation.isPending}
        danger
      >
        {deleting
          ? t('expenses.deleteText', {
              amount: formatMoney(deleting.amount, deleting.currencyCode, locale),
              category: t(`expenses.categories.${deleting.category}`),
            })
          : null}
      </ConfirmDialog>
    </div>
  );
}
