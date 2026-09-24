import { useState } from 'react';
import { useSessionDraft } from '@/features/auth/useSessionDraft';
import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { CarriedValues } from '@/features/collection/add/carried';
import { ApiError } from '@/shared/api/client';
import type { CurrencyOut, ExpenseCategory, ExpenseOut } from '@/shared/api/types';
import { currencySymbol, parseDecimal, todayIso } from '@/shared/lib/format';
import {
  Button,
  FormActions,
  FormError,
  FormRow,
  FormStack,
  Input,
  Select,
  Textarea,
} from '@/shared/ui';

import { MANUAL_CATEGORIES } from './api';

export interface ExpenseValues {
  category: ExpenseCategory;
  amount: string;
  currency: string;
  expenseDate: string;
  vendor: string | null;
  description: string | null;
  catalogItemId: number | null;
}

interface ExpenseFormProps {
  initial?: ExpenseOut;
  /** Preselected category; the "Додати" page sets it from its type selector. */
  category?: ExpenseCategory;
  /** Hidden when the page above already shows the type as its first field. */
  showCategory?: boolean;
  /**
   * The coin this expense is about — a whole picker, rendered by the page
   * that has one. Optional: a delivery need not be about any single coin.
   */
  coinField?: ReactNode;
  /**
   * The coin `coinField` currently points at. Left out — as the edit dialog
   * leaves it, having no picker — the expense keeps whatever link it already
   * had rather than losing it to a form that never asked.
   */
  catalogItemId?: number | null;
  /** Values shared with the purchase branch of the "Додати" page. */
  carried?: CarriedValues;
  onCarriedChange?: (values: CarriedValues) => void;
  currencies: CurrencyOut[];
  busy: boolean;
  submitError: unknown;
  onSubmit: (values: ExpenseValues) => void;
  onCancel: () => void;
}

interface Fields {
  category: ExpenseCategory;
  amount: string;
  currency: string;
  expenseDate: string;
  vendor: string;
  description: string;
}

type FieldErrors = Partial<Record<keyof Fields, string>>;

function carriedFrom(fields: Fields): CarriedValues {
  return {
    amount: fields.amount,
    currency: fields.currency,
    date: fields.expenseDate,
    vendor: fields.vendor,
    note: fields.description,
  };
}

export function ExpenseForm({
  initial,
  category,
  showCategory = true,
  coinField,
  catalogItemId,
  carried,
  onCarriedChange,
  currencies,
  busy,
  submitError,
  onSubmit,
  onCancel,
}: ExpenseFormProps) {
  const { t } = useTranslation();
  const [fields, setFields] = useSessionDraft<Fields>(`expense:${initial?.id ?? 'new'}`, {
    category: initial?.category ?? category ?? 'other',
    amount: initial?.amount ?? carried?.amount ?? '',
    currency: initial?.currencyCode ?? carried?.currency ?? 'UAH',
    expenseDate: initial?.expenseDate ?? carried?.date ?? todayIso(),
    vendor: initial?.vendor ?? carried?.vendor ?? '',
    description: initial?.description ?? carried?.note ?? '',
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const linkedCoinId =
    catalogItemId === undefined ? (initial?.catalogItemId ?? null) : catalogItemId;

  const set = (key: keyof Fields) => (value: string) => {
    const next = { ...fields, [key]: value };
    setFields(next);
    onCarriedChange?.(carriedFrom(next));
    setErrors((current) => ({ ...current, [key]: undefined }));
  };

  const rateMissing =
    submitError instanceof ApiError && submitError.problemType === 'exchange-rate-missing';
  const genericError =
    submitError && !rateMissing
      ? submitError instanceof ApiError && submitError.status === 409
        ? t('expenses.managedNote')
        : t('errors.generic')
      : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    const next: FieldErrors = {};
    const amount = parseDecimal(fields.amount);
    if (amount === null || amount <= 0) next.amount = 'expenses.amountInvalid';
    if (!fields.expenseDate) next.expenseDate = 'common.required';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    onSubmit({
      category: category ?? fields.category,
      amount: String(amount),
      currency: fields.currency,
      expenseDate: fields.expenseDate,
      vendor: fields.vendor.trim() || null,
      description: fields.description.trim() || null,
      catalogItemId: linkedCoinId,
    });
  }

  return (
    <form onSubmit={submit} noValidate data-testid="expense-form">
      <FormStack>
        <FormError>{genericError}</FormError>
        {showCategory ? (
          <Select
            label={t('expenses.category')}
            value={fields.category}
            onChange={(event) => set('category')(event.target.value)}
          >
            {MANUAL_CATEGORIES.map((option) => (
              <option key={option} value={option}>
                {t(`expenses.categories.${option}`)}
              </option>
            ))}
          </Select>
        ) : null}
        <FormRow>
          <Input
            label={t('expenses.amount', { symbol: currencySymbol(fields.currency) })}
            inputMode="decimal"
            required
            placeholder="0,00"
            value={fields.amount}
            onChange={(event) => set('amount')(event.target.value)}
            error={errors.amount ? t(errors.amount) : undefined}
          />
          <Select
            label={t('purchase.currency')}
            value={fields.currency}
            onChange={(event) => set('currency')(event.target.value)}
          >
            {(currencies.length ? currencies : [{ code: 'UAH', symbol: '₴' }]).map((currency) => (
              <option key={currency.code} value={currency.code}>
                {currency.code}
                {currency.symbol ? ` · ${currency.symbol}` : ''}
              </option>
            ))}
          </Select>
        </FormRow>
        <FormRow>
          <Input
            label={t('expenses.date')}
            type="date"
            required
            value={fields.expenseDate}
            onChange={(event) => set('expenseDate')(event.target.value)}
            error={
              errors.expenseDate
                ? t(errors.expenseDate)
                : rateMissing
                  ? t('purchase.rateMissing', { currency: fields.currency })
                  : undefined
            }
            hint={fields.currency !== 'UAH' ? t('purchase.rateHint') : undefined}
          />
          <Input
            label={t('expenses.vendor')}
            value={fields.vendor}
            onChange={(event) => set('vendor')(event.target.value)}
            placeholder={t('expenses.vendorPlaceholder')}
            maxLength={500}
          />
        </FormRow>
        <Textarea
          label={t('expenses.description')}
          value={fields.description}
          onChange={(event) => set('description')(event.target.value)}
          maxLength={4000}
        />
        {coinField}
        <FormActions>
          <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" loading={busy}>
            {initial ? t('common.save') : t('expenses.add')}
          </Button>
        </FormActions>
      </FormStack>
    </form>
  );
}
