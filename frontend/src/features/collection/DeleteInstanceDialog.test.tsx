import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CollectionItem } from '@/shared/api/types';

import { deleteCollectionItem } from './api';
import { DeleteInstanceDialog } from './DeleteInstanceDialog';

vi.mock('./api', () => ({ deleteCollectionItem: vi.fn() }));

const ITEM: CollectionItem = {
  id: 5,
  catalogItemId: 7,
  title: 'Дельфін',
  country: 'Україна',
  seriesName: null,
  denomination: '2 ₴',
  year: 2017,
  isArchived: false,
  archiveReason: null,
  quantity: 2,
  grade: 'UNC',
  purchaseDate: '2024-01-10',
  seller: null,
  price: '300.00',
  currency: 'UAH',
  rateUah: '1.0000',
  totalUah: '600.00',
  notes: null,
  thumbnailUrl: null,
  marketPriceUah: null,
};

describe('DeleteInstanceDialog', () => {
  it('names the purchase expense that goes with the instance and deletes on confirm', async () => {
    vi.mocked(deleteCollectionItem).mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <DeleteInstanceDialog item={ITEM} onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('delete-instance-text')).toHaveTextContent(
      '«Дельфін» буде видалено разом із витратою на покупку (600 ₴).',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Видалити' }));

    await waitFor(() => expect(deleteCollectionItem).toHaveBeenCalledWith(5));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
