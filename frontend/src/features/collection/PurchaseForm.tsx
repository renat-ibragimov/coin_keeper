import { useState } from 'react';
import { useSessionDraft } from '@/features/auth/useSessionDraft';
import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/shared/api/client';
import type { CollectionItem, CurrencyOut } from '@/shared/api/types';
import { currencySymbol, parseDecimal, todayIso } from '@/shared/lib/format';
import {
  Button,
  Combobox,
  FormActions,
  FormError,
  FormRow,
  FormStack,
  Input,
  Select,
  Textarea,
} from '@/shared/ui';

import type { CarriedValues } from './add/carried';
import { GRADES } from './grades';

export interface PurchaseValues {
  quantity: number;
  price: string;
  currency: string;
  purchaseDate: string;
  seller: string | null;
  grade: string | null;
  storageLocation: string | null;
  notes: string | null;
}

interface PurchaseFormProps {
  /** Existing instance when editing; absent for a new purchase. */
  initial?: CollectionItem;
  /**
   * What the "Додати" page carries over from the other branch of its type
   * selector; ignored while editing, where the instance itself is the source.
   */
  carried?: CarriedValues;
  onCarriedChange?: (values: CarriedValues) => void;
  /**
   * Checked after this form's own fields and before anything is sent: the
   * "Додати" page validates the coin it is about to create alongside the
   * purchase, and both sets of messages have to appear at once.
   */
  beforeSubmit?: () => boolean;
  /**
   * Rendered inside the form, last before the buttons: the "Додати" page puts
   * the purchase's supporting expenses there. It has to live inside the
   * <form> — those fields are submitted with the purchase, not beside it.
   */
  footer?: ReactNode;
  defaultGrade: string;
  defaultStorageLocation: string | null;
  storageLocations: string[];
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
  storageLocation: string;
  notes: string;
}

type FieldErrors = Partial<Record<keyof Fields, string>>;

function initialFields(
  initial: CollectionItem | undefined,
  defaultGrade: string,
  defaultStorageLocation: string | null,
  carried: CarriedValues | undefined,
): Fields {
  return {
    quantity: String(initial?.quantity ?? 1),
    // Zero, not blank: a coin found in change or handed over by a friend
    // cost nothing, and that is common enough that an empty field sends
    // those people back to fix a validation error every time (owner,
    // 2026-09-14). A real price is typed over it either way.
    // `||` on the carried half, not `??`: it starts as an empty string,
    // which `??` would happily keep.
    price: initial?.price ?? (carried?.amount || '0'),
    currency: initial?.currency ?? carried?.currency ?? 'UAH',
    purchaseDate: initial?.purchaseDate ?? carried?.date ?? todayIso(),
    seller: initial?.seller ?? carried?.vendor ?? '',
    grade: initial?.grade ?? defaultGrade,
    storageLocation: initial?.storageLocation ?? defaultStorageLocation ?? '',
    notes: initial?.notes ?? carried?.note ?? '',
  };
}

function carriedFrom(fields: Fields): CarriedValues {
  return {
    amount: fields.price,
    currency: fields.currency,
    date: fields.purchaseDate,
    vendor: fields.seller,
    note: fields.notes,
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
  carried,
  onCarriedChange,
  beforeSubmit,
  footer,
  defaultGrade,
  defaultStorageLocation,
  storageLocations,
  currencies,
  busy,
  submitError,
  onSubmit,
  onCancel,
}: PurchaseFormProps) {
  const { t } = useTranslation();
  const [fields, setFields] = useSessionDraft<Fields>(`purchase:${initial?.id ?? 'new'}`, () =>
    initialFields(initial, defaultGrade, defaultStorageLocation, carried),
  );
  const [errors, setErrors] = useState<FieldErrors>({});

  const set = (key: keyof Fields) => (value: string) => {
    const next = { ...fields, [key]: value };
    setFields(next);
    // Reported outward rather than folded into the state updater: the page
    // above keeps this in its own state, and a parent must not be told to
    // update from inside one.
    onCarriedChange?.(carriedFrom(next));
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
    // Both run, whatever the first one says: a person fixing the form should
    // see everything that is wrong with it, not one message at a time.
    const coinOk = beforeSubmit ? beforeSubmit() : true;
    if (Object.keys(next).length > 0 || !coinOk) return;
    onSubmit({
      quantity: Number.parseInt(fields.quantity, 10),
      price: String(parseDecimal(fields.price)),
      currency: fields.currency,
      purchaseDate: fields.purchaseDate,
      seller: fields.seller.trim() || null,
      grade: fields.grade.trim() || null,
      storageLocation: fields.storageLocation.trim() || null,
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
            // The default 0 is selected the moment the field is focused, so
            // typing a real price replaces it instead of landing beside it
            // ("0250"). Only the untouched zero: a price already typed is
            // left alone, so a stray click does not wipe it.
            onFocus={(event) => {
              if (event.target.value === '0') event.target.select();
            }}
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
        <Combobox
          label={t('purchase.storageLocation')}
          placeholder={t('purchase.storageLocationPlaceholder')}
          options={storageLocations}
          value={fields.storageLocation}
          onChange={(event) => set('storageLocation')(event.target.value)}
          maxLength={200}
        />
        <Textarea
          label={t('purchase.notes')}
          placeholder={t('purchase.notesPlaceholder')}
          value={fields.notes}
          onChange={(event) => set('notes')(event.target.value)}
          maxLength={4000}
        />
        {footer}
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
