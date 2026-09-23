import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { ApiError } from '@/shared/api/client';

import { PurchaseForm } from './PurchaseForm';

const CURRENCIES = [
  { code: 'UAH', name: 'Hryvnia', symbol: '₴', decimalPlaces: 2 },
  { code: 'USD', name: 'Dollar', symbol: '$', decimalPlaces: 2 },
];

function renderForm(overrides: Partial<Parameters<typeof PurchaseForm>[0]> = {}) {
  const onSubmit = vi.fn();
  render(
    <PurchaseForm
      defaultGrade="UNC"
      defaultStorageLocation={null}
      storageLocations={['Вдома', 'В дорозі']}
      currencies={CURRENCIES}
      busy={false}
      submitError={null}
      onSubmit={onSubmit}
      onCancel={() => {}}
      {...overrides}
    />,
  );
  return onSubmit;
}

describe('PurchaseForm', () => {
  it('starts with today, one piece, hryvnia and the default grade', () => {
    renderForm();
    expect(screen.getByLabelText('Кількість')).toHaveValue(1);
    expect(screen.getByLabelText('Валюта')).toHaveTextContent('UAH');
    expect(screen.getByLabelText('Стан')).toHaveTextContent('UNC');
    expect((screen.getByLabelText('Дата покупки') as HTMLInputElement).value).toMatch(
      /^\d{4}-\d{2}-\d{2}$/,
    );
  });

  it('refuses an emptied price and a zero quantity without calling the API', async () => {
    const onSubmit = renderForm();
    await userEvent.clear(screen.getByLabelText('Кількість'));
    await userEvent.type(screen.getByLabelText('Кількість'), '0');
    // The price starts at 0 and is valid; emptying it is what the check is for.
    await userEvent.clear(screen.getByLabelText(/Ціна за шт/));
    await userEvent.click(screen.getByRole('button', { name: 'Додати монету' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Кількість — ціле число від 1.')).toBeInTheDocument();
    expect(screen.getByText('Вкажіть ціну числом, не менше 0.')).toBeInTheDocument();
  });

  it('submits normalised values: a decimal comma price and trimmed text', async () => {
    const onSubmit = renderForm();
    await userEvent.type(screen.getByLabelText(/Ціна за шт/), '1 250,50');
    await userEvent.type(screen.getByLabelText('Продавець'), '  Violity  ');
    await userEvent.type(screen.getByLabelText('Місце зберігання'), '  Вдома  ');
    await userEvent.click(screen.getByRole('button', { name: 'Додати монету' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        quantity: 1,
        price: '1250.5',
        currency: 'UAH',
        seller: 'Violity',
        grade: 'UNC',
        storageLocation: 'Вдома',
        notes: null,
      }),
    );
  });

  it('pre-fills the storage location from settings for a new purchase', () => {
    renderForm({ defaultStorageLocation: 'В дорозі' });
    expect(screen.getByLabelText('Місце зберігання')).toHaveValue('В дорозі');
  });

  it('shows a missing NBU rate under the date field, naming the currency', () => {
    renderForm({
      submitError: new ApiError(422, {
        type: 'https://coinkeeper.app/problems/exchange-rate-missing',
        detail: 'No NBU rate for USD on or before 2001-01-01',
      }),
      initial: {
        id: 1,
        catalogItemId: 7,
        title: 'Дельфін',
        country: 'Україна',
        seriesName: null,
        denomination: null,
        year: 2017,
        isArchived: false,
        archiveReason: null,
        quantity: 1,
        grade: null,
        purchaseDate: '2001-01-01',
        seller: null,
        price: '10.00',
        currency: 'USD',
        rateUah: null,
        totalUah: '0.00',
        storageLocation: null,
        notes: null,
        thumbnailUrl: null,
        obversePhotoIsOwn: false,
        reversePhotoIsOwn: false,
        marketPriceUah: null,
      },
    });
    expect(screen.getByLabelText('Дата покупки')).toBeInvalid();
    expect(
      screen.getByText('На цю дату немає курсу НБУ для USD. Оберіть іншу дату або валюту.'),
    ).toBeInTheDocument();
  });
});

describe('PurchaseForm price default', () => {
  it('starts at zero so a found or gifted coin needs no correction', () => {
    renderForm();
    expect(screen.getByLabelText(/Ціна за шт/)).toHaveValue('0');
  });

  it('submits that zero without complaining', async () => {
    const onSubmit = renderForm();
    await userEvent.click(screen.getByRole('button', { name: 'Додати монету' }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ price: '0' }));
  });

  it('keeps an existing purchase price when editing', () => {
    renderForm({
      initial: {
        id: 1,
        catalogItemId: 1,
        price: '150.50',
        quantity: 1,
      } as never,
    });
    expect(screen.getByLabelText(/Ціна за шт/)).toHaveValue('150.50');
  });
});

describe('PurchaseForm price entry', () => {
  it('replaces the default zero instead of letting a price land beside it', async () => {
    const onSubmit = renderForm();
    await userEvent.type(screen.getByLabelText(/Ціна за шт/), '250');

    expect(screen.getByLabelText(/Ціна за шт/)).toHaveValue('250');
    await userEvent.click(screen.getByRole('button', { name: 'Додати монету' }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ price: '250' }));
  });

  it('leaves a price that is already typed alone when the field is focused again', async () => {
    renderForm();
    const price = screen.getByLabelText(/Ціна за шт/);
    await userEvent.type(price, '250');
    await userEvent.click(screen.getByLabelText('Продавець'));
    await userEvent.type(price, '0');

    // Appending, not replacing: only the untouched zero gets selected.
    expect(price).toHaveValue('2500');
  });
});
