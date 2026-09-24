import { ChevronDown, X } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { MANUAL_CATEGORIES } from '@/features/expenses/api';
import type { CurrencyOut, ExpenseCategory } from '@/shared/api/types';
import { currencySymbol } from '@/shared/lib/format';
import { Input, Select } from '@/shared/ui';

import { newExtraExpense } from './extraExpenseRows';
import type { ExtraExpenseErrors, ExtraExpenseRow } from './extraExpenseRows';
import styles from './ExtraExpenses.module.css';

interface ExtraExpensesProps {
  rows: ExtraExpenseRow[];
  onChange: (rows: ExtraExpenseRow[]) => void;
  /** Keyed by row key, not by position: rows come and go. */
  errors: ExtraExpenseErrors;
  currencies: CurrencyOut[];
  /** The purchase's own currency, which a new row starts out sharing. */
  defaultCurrency: string;
}

/**
 * "Пов'язані витрати" — the supporting expenses of this purchase, folded away
 * at the bottom of the form.
 *
 * Delivery, a holder, a grading fee: money spent on the coin at the moment it
 * was bought, which until now meant going to «Гроші» afterwards and writing it
 * down a second time — which is to say, usually not writing it down at all
 * (owner's call, 2026-09-14). The whole lot goes in the same request as the
 * purchase (`extraExpenses`, docs/api.md).
 *
 * The date and the seller are not asked for again: an expense recorded here
 * takes both from the purchase. What comes back is an ordinary manual expense
 * linked to the coin — the journal edits and deletes it like any other, and
 * deleting it leaves the coin alone.
 */
export function ExtraExpenses({
  rows,
  onChange,
  errors,
  currencies,
  defaultCurrency,
}: ExtraExpensesProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const toggle = () => {
    const next = !expanded;
    setExpanded(next);
    // Opening an empty block on an empty row would be a section that looks
    // broken; opening it *with* one is the invitation to use it.
    if (next && rows.length === 0) onChange([newExtraExpense(defaultCurrency)]);
  };

  const update = (key: number, patch: Partial<ExtraExpenseRow>) => {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  };

  const options = currencies.length ? currencies : [{ code: 'UAH', name: 'UAH', symbol: '₴' }];

  return (
    <div className={styles.block}>
      <button
        type="button"
        className={styles.toggle}
        onClick={toggle}
        aria-expanded={expanded}
        aria-controls="add-extra-expenses"
      >
        <ChevronDown
          strokeWidth={2}
          className={[styles.chevron, expanded ? styles.chevronOpen : ''].filter(Boolean).join(' ')}
          aria-hidden="true"
        />
        {t('add.extraExpenses')}
      </button>

      <div id="add-extra-expenses" className={styles.rows} hidden={!expanded}>
        <p className={styles.lead}>{t('add.extraExpensesLead')}</p>
        {rows.map((row) => (
          <div key={row.key} className={styles.row}>
            <Select
              label={t('expenses.category')}
              value={row.category}
              onChange={(event) =>
                update(row.key, { category: event.target.value as ExpenseCategory })
              }
            >
              {MANUAL_CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {t(`expenses.categories.${category}`)}
                </option>
              ))}
            </Select>
            <Input
              label={t('expenses.amount', { symbol: currencySymbol(row.currency) })}
              type="text"
              inputMode="decimal"
              placeholder="0,00"
              value={row.amount}
              onChange={(event) => update(row.key, { amount: event.target.value })}
              error={errors[row.key]}
            />
            <Select
              label={t('purchase.currency')}
              value={row.currency}
              onChange={(event) => update(row.key, { currency: event.target.value })}
            >
              {options.map((currency) => (
                <option key={currency.code} value={currency.code}>
                  {currency.code}
                  {currency.symbol ? ` · ${currency.symbol}` : ''}
                </option>
              ))}
            </Select>
            <button
              type="button"
              className={styles.remove}
              aria-label={t('add.extraExpenseRemove')}
              onClick={() => onChange(rows.filter((other) => other.key !== row.key))}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
        ))}
        <button
          type="button"
          className={styles.add}
          onClick={() => onChange([...rows, newExtraExpense(defaultCurrency)])}
        >
          {t('add.extraExpenseAdd')}
        </button>
      </div>
    </div>
  );
}
