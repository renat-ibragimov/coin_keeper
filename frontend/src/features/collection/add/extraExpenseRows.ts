/**
 * The supporting expenses of a purchase, as data: one row per expense, and
 * the rule for turning rows into a request.
 *
 * Kept apart from the component that renders them for the same reason
 * `carried.ts` and `coinFields.ts` are — the "Додати" page reads and
 * validates these without rendering anything.
 */
import type { CollectionItemCreate, ExpenseCategory } from '@/shared/api/types';
import { parseDecimal } from '@/shared/lib/format';

export interface ExtraExpenseRow {
  /** Stable across re-renders and removals, unlike the array index. */
  key: number;
  category: ExpenseCategory;
  amount: string;
  currency: string;
}

export type ExtraExpenseErrors = Record<number, string>;

type ExtraExpenseIn = NonNullable<CollectionItemCreate['extraExpenses']>[number];

/**
 * What the rows amount to as a request, and what is wrong with them.
 *
 * A row whose amount was never filled in is dropped rather than rejected:
 * opening the block adds an empty row, and someone who opens it out of
 * curiosity and submits should not be stopped. A row with something typed in
 * it is a real intention, so an unreadable or non-positive amount is an error
 * on that row — zero included, unlike the coin's own price (`gt=0` on the
 * server, docs/api.md).
 */
export function collectExtraExpenses(rows: ExtraExpenseRow[]): {
  values: ExtraExpenseIn[];
  errors: ExtraExpenseErrors;
} {
  const values: ExtraExpenseIn[] = [];
  const errors: ExtraExpenseErrors = {};
  for (const row of rows) {
    if (!row.amount.trim()) continue;
    const amount = parseDecimal(row.amount);
    if (amount === null || amount <= 0) {
      errors[row.key] = 'add.extraExpenseAmountInvalid';
      continue;
    }
    values.push({ category: row.category, amount: String(amount), currency: row.currency });
  }
  return { values, errors };
}

let nextKey = 0;

export function newExtraExpense(currency: string): ExtraExpenseRow {
  nextKey += 1;
  return { key: nextKey, category: 'delivery', amount: '', currency };
}
