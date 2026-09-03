import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/shared/api/client';
import type { CollectionItem, CurrencyOut } from '@/shared/api/types';
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

import { GRADES } from './grades';

export interface PurchaseValues {
  quantity: number;
  price: string;
  currency: string;
  purchaseDate: string;
  seller: string | null;
  grade: string | null;
  notes: string | null;
}

interface PurchaseFormProps {
  /** Existing instance when editing; absent for a new purchase. */
  initial?: CollectionItem;
  defaultGrade: string;
  currencies: CurrencyOut[];
  busy: boolean;
  /** The last failed submission: rate and currency problems land on their fields. */
  submitError: unknown;
  onSubmit: (values: PurchaseValues) => void;
  onCancel: () => void;
}

interface Fields {
  quantity: string;
  price: string;
  currency: string;
  purchaseDate: string;
  seller: string;
  grade: string;
  notes: string;
}

type FieldErrors = Partial<Record<keyof Fields, string>>;

function initialFields(initial: CollectionItem | undefined, defaultGrade: string): Fields {
  return {
    quantity: String(initial?.quantity ?? 1),
    price: initial?.price ?? '',
    currency: initial?.currency ?? 'UAH',
    purchaseDate: initial?.purchaseDate ?? todayIso(),
    seller: initial?.seller ?? '',
    grade: initial?.grade ?? defaultGrade,
    notes: initial?.notes ?? '',
  };
}

/** Which field a rejected submission belongs to; empty for a generic failure. */
function serverFieldErrors(error: unknown, currency: string): FieldErrors {
  if (!(error instanceof ApiError)) return {};
  if (error.problemType === 'exchange-rate-missing') {
    return { purchaseDate: `purchase.rateMissing:${currency}` };
  }
  if (error.problemType === 'unknown-currency') return { currency: 'purchase.unknownCurrency' };
  return {};
}

export function PurchaseForm({
  initial,
  defaultGrade,
  currencies,
  busy,
  submitError,
  onSubmit,
  onCancel,
}: PurchaseFormProps) {
  const { t } = useTranslation();
  const [fields, setFields] = useState<Fields>(() => initialFields(initial, defaultGrade));
  const [errors, setErrors] = useState<FieldErrors>({});

  const set = (key: keyof Fields) => (value: string) => {
    setFields((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  };

  const serverErrors = serverFieldErrors(submitError, fields.currency);
  const message = (key: keyof Fields): string | undefined => {
    const own = errors[key];
    if (own) return t(own);
    const server = serverErrors[key];
    if (!server) return undefined;
    const [translationKey, currency] = server.split(':');
    return t(translationKey!, { currency });
  };
  const genericError =
    submitError && Object.keys(serverErrors).length === 0
      ? submitError instanceof ApiError && submitError.status === 404
        ? t('card.notFoundTitle')
        : t('errors.generic')
      : null;

  const foreign = fields.currency !== 'UAH';
  const gradeOptions =
    fields.grade && !GRADES.includes(fields.grade as (typeof GRADES)[number])
      ? [fields.grade, ...GRADES]
      : [...GRADES];

  function validate(): FieldErrors {
    const next: FieldErrors = {};
    const quantity = Number.parseInt(fields.quantity, 10);
    if (!Number.isInteger(quantity) || quantity < 1) next.quantity = 'purchase.quantityInvalid';
    const price = parseDecimal(fields.price);
    if (price === null || price < 0) next.price = 'purchase.priceInvalid';
    if (!fields.purchaseDate) next.purchaseDate = 'common.required';
    if (!fields.currency) next.currency = 'common.required';
    return next;
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    onSubmit({
      quantity: Number.parseInt(fields.quantity, 10),
      price: String(parseDecimal(fields.price)),
      currency: fields.currency,
      purchaseDate: fields.purchaseDate,
      seller: fields.seller.trim() || null,
      grade: fields.grade.trim() || null,
      notes: fields.notes.trim() || null,
    });
  }

  return (
    <form onSubmit={submit} noValidate data-testid="purchase-form">
      <FormStack>
        <FormError>{genericError}</FormError>
        <FormRow>
          <Input
            label={t('purchase.quantity')}
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            required
            value={fields.quantity}
            onChange={(event) => set('quantity')(event.target.value)}
            error={message('quantity')}
          />
          <Input
            label={t('purchase.date')}
            type="date"
            required
            value={fields.purchaseDate}
            onChange={(event) => set('purchaseDate')(event.target.value)}
            error={message('purchaseDate')}
            hint={foreign ? t('purchase.rateHint') : undefined}
          />
        </FormRow>
        <FormRow>
          <Input
            label={t('purchase.price', { symbol: currencySymbol(fields.currency) })}
            type="text"
            inputMode="decimal"
            required
            placeholder="0,00"
            value={fields.price}
            onChange={(event) => set('price')(event.target.value)}
            error={message('price')}
          />
          <Select
            label={t('purchase.currency')}
            value={fields.currency}
            onChange={(event) => set('currency')(event.target.value)}
            error={message('currency')}
          >
            {(currencies.length ? currencies : [{ code: 'UAH', name: 'UAH', symbol: '₴' }]).map(
              (currency) => (
                <option key={currency.code} value={currency.code}>
                  {currency.code}
                  {currency.symbol ? ` · ${currency.symbol}` : ''}
                </option>
              ),
            )}
          </Select>
        </FormRow>
        <FormRow>
          <Input
            label={t('purchase.seller')}
            placeholder={t('purchase.sellerPlaceholder')}
            value={fields.seller}
            onChange={(event) => set('seller')(event.target.value)}
            maxLength={500}
          />
          <Select
            label={t('purchase.grade')}
            value={fields.grade}
            onChange={(event) => set('grade')(event.target.value)}
          >
            <option value="">{t('purchase.gradeNone')}</option>
            {gradeOptions.map((grade) => (
              <option key={grade} value={grade}>
                {grade}
              </option>
            ))}
          </Select>
        </FormRow>
        <Textarea
          label={t('purchase.notes')}
          placeholder={t('purchase.notesPlaceholder')}
          value={fields.notes}
          onChange={(event) => set('notes')(event.target.value)}
          maxLength={4000}
        />
        <FormActions>
          <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" loading={busy}>
            {initial ? t('common.save') : t('purchase.submit')}
          </Button>
        </FormActions>
      </FormStack>
    </form>
  );
}
