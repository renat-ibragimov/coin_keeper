import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { fetchCurrencies } from '@/features/catalog/api';
import { ApiError } from '@/shared/api/client';
import type { ExpenseCategory, ExpenseOut } from '@/shared/api/types';
import { formatDate, formatMoney, formatUah } from '@/shared/lib/format';
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
  Pagination,
  Skeleton,
  StatTile,
  useToast,
} from '@/shared/ui';

import {
  ALL_CATEGORIES,
  createExpense,
  deleteExpense,
  fetchExpenses,
  fetchExpensesSummary,
  PAGE_SIZE,
  updateExpense,
} from './api';
import { ExpenseForm } from './ExpenseForm';
import type { ExpenseValues } from './ExpenseForm';
import styles from './ExpensesPage.module.css';

const DEPENDENT_KEYS = ['expenses', 'bootstrap'];

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
  const [editor, setEditor] = useState<Editor>({ mode: 'closed' });
  const [deleting, setDeleting] = useState<ExpenseOut | null>(null);

  const listQuery = useQuery({
    queryKey: ['expenses', 'list', category, page],
    queryFn: () => fetchExpenses({ category, page }),
    placeholderData: keepPreviousData,
  });
  const summaryQuery = useQuery({
    queryKey: ['expenses', 'summary'],
    queryFn: fetchExpensesSummary,
  });
  const currenciesQuery = useQuery({ queryKey: ['currencies'], queryFn: fetchCurrencies });

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

  const setFilter = (changes: { category?: ExpenseCategory; page?: number }) => {
    const next = new URLSearchParams(params);
    if ('category' in changes) {
      if (changes.category) next.set('category', changes.category);
      else next.delete('category');
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
  const list = listQuery.data;
  const pageCount = Math.max(1, Math.ceil((list?.total ?? 0) / PAGE_SIZE));

  return (
    <div className={styles.page}>
      <PageHeader
        title={t('expenses.title')}
        subtitle={t('expenses.subtitle')}
        actions={
          <Button onClick={() => setEditor({ mode: 'create' })}>+ {t('expenses.add')}</Button>
        }
      />

      <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
        {summary ? (
          <>
            <StatTile label={t('expenses.tileTotal')} value={formatUah(summary.totalUah, locale)} />
            <StatTile
              label={t('expenses.tileCoins')}
              value={formatUah(coins?.totalUah ?? '0', locale)}
              hint={t('expenses.count', { count: coins?.count ?? 0 })}
            />
            <StatTile
              label={t('expenses.tileRelated')}
              value={formatUah(relatedUah, locale)}
              hint={t('expenses.count', {
                count: summary.categories
                  .filter((row) => row.category !== 'coin_purchase')
                  .reduce((sum, row) => sum + row.count, 0),
              })}
            />
          </>
        ) : (
          Array.from({ length: 3 }, (_, index) => <Skeleton key={index} height={96} />)
        )}
      </section>

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
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>{t('expenses.date')}</th>
                <th>{t('expenses.category')}</th>
                <th>{t('expenses.description')}</th>
                <th>{t('expenses.vendor')}</th>
                <th className={styles.number}>{t('expenses.amountHeader')}</th>
                <th className={styles.number}>₴</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.items.map((expense) => {
                const fromPurchase = expense.category === 'coin_purchase';
                return (
                  <tr key={expense.id}>
                    <td className="tabular">{formatDate(expense.expenseDate, locale)}</td>
                    <td>
                      <Badge tone={fromPurchase ? 'accent' : 'neutral'}>
                        {t(`expenses.categories.${expense.category}`)}
                      </Badge>
                    </td>
                    <td>
                      {fromPurchase && expense.catalogItemId ? (
                        <Link to={`/catalog/${expense.catalogItemId}`}>
                          {expense.description || t('expenses.fromPurchase')}
                        </Link>
                      ) : (
                        expense.description || '—'
                      )}
                    </td>
                    <td>{expense.vendor || '—'}</td>
                    <td className={`${styles.number} tabular`}>
                      {formatMoney(expense.amount, expense.currencyCode, locale)}
                    </td>
                    <td className={`${styles.number} tabular`}>
                      {formatUah(expense.amountUah, locale)}
                    </td>
                    <td className={styles.actions}>
                      {fromPurchase ? (
                        <span className={styles.managed} title={t('expenses.managedNote')}>
                          {t('expenses.fromPurchase')}
                        </span>
                      ) : (
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
          </table>
        </div>
      ) : null}
      <Pagination
        page={page}
        pageCount={pageCount}
        onChange={(next) => setFilter({ page: next })}
      />

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
