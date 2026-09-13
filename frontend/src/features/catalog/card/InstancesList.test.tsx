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
          addHref="/collection/coins/new?catalogItemId=7"
          coinTitle="Дельфін"
          photo={{ src: null }}
          currentPriceUah="460.00"
          usdRate={41.5}
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

  it('shows the purchase total, the historical rate, and a dash for the storage place', () => {
    renderList();
    expect(screen.getByText('350 ₴')).toBeInTheDocument();
    expect(screen.getByText('35 ₴ за 1 $')).toBeInTheDocument();
    const row = screen.getByTestId('instance-row');
    // "Місце зберігання" has no field yet — every row shows a dash.
    expect(row.textContent).toContain('—');
  });

  it('shows the seller, the ownership duration, and a ≈$ by the live rate next to every UAH figure', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-13T00:00:00Z'));
    try {
      renderList();

      expect(screen.getByText('Аукціон Violity')).toBeInTheDocument();
      // 529 days between the purchase and "today" — one full year.
      expect(screen.getByText('1 рік')).toBeInTheDocument();

      // purchaseTotal 350, currentValue 460 (quantity 1), change +110, at usdRate=41.5.
      expect(screen.getByText('≈ 8,4 $')).toBeInTheDocument();
      expect(screen.getByText('≈ 11,1 $')).toBeInTheDocument();
      expect(screen.getByText('≈ +2,7 $')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows "no data" instead of a ≈$ guess when NBU has no rate yet', () => {
    renderList({ usdRate: null });
    expect(screen.getAllByText('немає даних').length).toBeGreaterThan(0);
    expect(screen.queryByText(/≈/)).not.toBeInTheDocument();
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
