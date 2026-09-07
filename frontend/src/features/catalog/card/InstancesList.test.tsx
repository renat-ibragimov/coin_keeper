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

function renderList() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <InstancesList
          items={INSTANCES}
          loading={false}
          addHref="/collection/coins/new?catalogItemId=7"
          coinTitle="Дельфін"
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
