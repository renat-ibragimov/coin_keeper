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
    expect(screen.getByLabelText('Валюта')).toHaveValue('UAH');
    expect(screen.getByLabelText('Стан')).toHaveValue('UNC');
    expect((screen.getByLabelText('Дата покупки') as HTMLInputElement).value).toMatch(
      /^\d{4}-\d{2}-\d{2}$/,
    );
  });

  it('refuses an empty price and a zero quantity without calling the API', async () => {
    const onSubmit = renderForm();
    await userEvent.clear(screen.getByLabelText('Кількість'));
    await userEvent.type(screen.getByLabelText('Кількість'), '0');
    await userEvent.click(screen.getByRole('button', { name: 'Додати покупку' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Кількість — ціле число від 1.')).toBeInTheDocument();
    expect(screen.getByText('Вкажіть ціну числом, не менше 0.')).toBeInTheDocument();
  });

  it('submits normalised values: a decimal comma price and trimmed text', async () => {
    const onSubmit = renderForm();
    await userEvent.type(screen.getByLabelText(/Ціна за шт/), '1 250,50');
    await userEvent.type(screen.getByLabelText('Продавець'), '  Violity  ');
    await userEvent.click(screen.getByRole('button', { name: 'Додати покупку' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        quantity: 1,
        price: '1250.5',
        currency: 'UAH',
        seller: 'Violity',
        grade: 'UNC',
        notes: null,
      }),
    );
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
        notes: null,
        thumbnailUrl: null,
        marketPriceUah: null,
      },
    });
    expect(screen.getByLabelText('Дата покупки')).toBeInvalid();
    expect(
      screen.getByText('На цю дату немає курсу НБУ для USD. Оберіть іншу дату або валюту.'),
    ).toBeInTheDocument();
  });
});
