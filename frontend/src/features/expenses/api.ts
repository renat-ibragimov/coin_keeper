import { api, toQuery } from '@/shared/api/client';
import type {
  ExpenseCategory,
  ExpenseCreate,
  ExpenseOut,
  ExpensePage,
  ExpensesSummary,
  ExpenseUpdate,
} from '@/shared/api/types';

export const PAGE_SIZE = 24;

/** Categories a person records by hand; coin_purchase rows come from purchases only. */
export const MANUAL_CATEGORIES: ExpenseCategory[] = [
  'delivery',
  'album',
  'holder',
  'storage',
  'grading',
  'literature',
  'photo_equipment',
  'other',
];

export const ALL_CATEGORIES: ExpenseCategory[] = ['coin_purchase', ...MANUAL_CATEGORIES];

/** Every column of the journal sorts (docs/08-ui-map.md). */
export const EXPENSE_SORTS = ['date', 'category', 'description', 'vendor', 'amount'] as const;
export type ExpenseSort = (typeof EXPENSE_SORTS)[number];

export interface ExpenseFilters {
  category?: ExpenseCategory;
  page: number;
  sort: ExpenseSort;
  order: 'asc' | 'desc';
}

export function fetchExpenses(filters: ExpenseFilters): Promise<ExpensePage> {
  return api<ExpensePage>(
    `/expenses${toQuery({
      category: filters.category,
      page: filters.page,
      pageSize: PAGE_SIZE,
      sort: filters.sort,
      order: filters.order,
    })}`,
  );
}

export function fetchExpensesSummary(): Promise<ExpensesSummary> {
  return api<ExpensesSummary>('/expenses/summary');
}

export function createExpense(body: ExpenseCreate): Promise<ExpenseOut> {
  return api<ExpenseOut>('/expenses', { method: 'POST', body });
}

export function updateExpense(id: number, body: ExpenseUpdate): Promise<ExpenseOut> {
  return api<ExpenseOut>(`/expenses/${id}`, { method: 'PATCH', body });
}

export function deleteExpense(id: number): Promise<void> {
  return api<void>(`/expenses/${id}`, { method: 'DELETE' });
}
