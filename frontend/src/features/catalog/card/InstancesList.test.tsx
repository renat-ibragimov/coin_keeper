import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { deleteCollectionItem } from '@/features/collection/api';
import type { CatalogCollectionItem } from '@/shared/api/types';

import { InstancesList } from './InstancesList';

vi.mock('@/features/collection/api', () => ({ deleteCollectionItem: vi.fn() }));

const INSTANCES: CatalogCollectionItem[] = [
  {
    id: 1,
    catalogItemId: 7,
    quantity: 1,
    grade: 'UNC',
    acquisitionDate: '2025-04-02',
    seller: 'Аукціон Violity',
    purchasePrice: '10.00',
    purchaseCurrency: 'USD',
    purchaseRateUah: '35.0000',
    totalUah: '350.00',
    // Independent of purchaseRateUah on purpose: totalUsd/totalEur are the
    // backend's own NBU-rate-on-purchase-date conversions, not a mirror of
    // the purchase's own currency math (see InstancesList's secondaryRate
    // prop doc).
    totalUsd: '8.40',
    totalEur: '7.70',
    supportingExpensesUah: null,
    storageLocation: 'Вдома',
    notes: null,
  },
];

function renderList(overrides: Partial<Parameters<typeof InstancesList>[0]> = {}) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <InstancesList
          items={INSTANCES}
          loading={false}
          addHref="/collection/add?catalogItemId=7"
          coinTitle="Дельфін"
          photo={{ src: null }}
          currentPriceUah="460.00"
          secondaryCurrency="USD"
          secondaryRate={41.5}
          {...overrides}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InstancesList', () => {
  it('links each purchase to its own edit form', () => {
    renderList();
    expect(screen.getByRole('link', { name: 'Редагувати' })).toHaveAttribute(
      'href',
      '/collection/coins/1/edit',
    );
  });

  it('shows the purchase total, the historical rate, and the storage place', () => {
    renderList();
    expect(screen.getByText('350 ₴')).toBeInTheDocument();
    expect(screen.getByText('35 ₴ за 1 $')).toBeInTheDocument();
    expect(screen.getByText('Вдома')).toBeInTheDocument();
  });

  it('shows a dash when a purchase has no storage location', () => {
    renderList({ items: [{ ...INSTANCES[0]!, storageLocation: null }] });
    const row = screen.getByTestId('instance-row');
    expect(row.textContent).toContain('—');
  });

  it('shows the seller, the ownership duration, and a ≈$ next to every UAH figure', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-13T00:00:00Z'));
    try {
      renderList();

      expect(screen.getByText('Аукціон Violity')).toBeInTheDocument();
      // 529 days between the purchase and "today" — one full year.
      expect(screen.getByText('1 рік')).toBeInTheDocument();

      // Purchased total: item.totalUsd (8.40) — the backend's historical-rate
      // conversion, not a division by secondaryRate.
      expect(screen.getByText('≈ 8,4 $')).toBeInTheDocument();
      // Current value: 460 (quantity 1) at the live secondaryRate=41.5 -> 11.08.
      expect(screen.getByText('≈ 11,1 $')).toBeInTheDocument();
      // Change: 11.08 (current, live rate) − 8.40 (purchased, historical) = 2.68.
      expect(screen.getByText('≈ +2,7 $')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps the purchased total in dollars when only the live rate is missing', () => {
    // secondaryRate feeds current value/change, not the purchased total (item.totalUsd) --
    // losing today's rate should not blank out what was already known historically.
    renderList({ secondaryRate: null });
    expect(screen.getByText('≈ 8,4 $')).toBeInTheDocument();
    expect(screen.getAllByText('немає даних').length).toBe(2); // current value, change
  });

  it('shows "no data" for the purchased total and the change when NBU has no rate that far back', () => {
    renderList({ items: [{ ...INSTANCES[0]!, totalUsd: null }] });
    // Current value still resolves from the live rate; change needs both
    // sides of the subtraction, so it goes unknown along with the total.
    expect(screen.getByText('≈ 11,1 $')).toBeInTheDocument();
    expect(screen.getAllByText('немає даних').length).toBe(2); // purchased total, change
  });

  it('confirms and deletes a purchase, naming the coin in the confirmation', async () => {
    vi.mocked(deleteCollectionItem).mockResolvedValue(undefined);
    renderList();

    await userEvent.click(screen.getByRole('button', { name: 'Видалити' }));
    expect(screen.getByTestId('delete-instance-text')).toHaveTextContent(
      '«Дельфін» буде видалено разом із витратою на покупку (350 ₴).',
    );

    await userEvent.click(screen.getAllByRole('button', { name: 'Видалити' })[1]!);
    await waitFor(() => expect(deleteCollectionItem).toHaveBeenCalledWith(1));
  });
});
