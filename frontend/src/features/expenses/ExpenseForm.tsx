import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

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
}

interface ExpenseFormProps {
  initial?: ExpenseOut;
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

export function ExpenseForm({
  initial,
  currencies,
  busy,
  submitError,
  onSubmit,
  onCancel,
}: ExpenseFormProps) {
  const { t } = useTranslation();
  const [fields, setFields] = useState<Fields>({
    category: initial?.category ?? 'other',
    amount: initial?.amount ?? '',
    currency: initial?.currencyCode ?? 'UAH',
    expenseDate: initial?.expenseDate ?? todayIso(),
    vendor: initial?.vendor ?? '',
    description: initial?.description ?? '',
  });
  const [errors, setErrors] = useState<FieldErrors>({});

  const set = (key: keyof Fields) => (value: string) => {
    setFields((current) => ({ ...current, [key]: value }));
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
      category: fields.category,
      amount: String(amount),
      currency: fields.currency,
      expenseDate: fields.expenseDate,
      vendor: fields.vendor.trim() || null,
      description: fields.description.trim() || null,
    });
  }

  return (
    <form onSubmit={submit} noValidate data-testid="expense-form">
      <FormStack>
        <FormError>{genericError}</FormError>
        <Select
          label={t('expenses.category')}
          value={fields.category}
          onChange={(event) => set('category')(event.target.value)}
        >
          {MANUAL_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {t(`expenses.categories.${category}`)}
            </option>
          ))}
        </Select>
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
