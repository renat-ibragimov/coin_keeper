import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { deleteCollectionItem } from './api';
import { DeleteInstanceDialog } from './DeleteInstanceDialog';

vi.mock('./api', () => ({ deleteCollectionItem: vi.fn() }));

const ITEM = { id: 5, title: 'Дельфін', totalUah: '600.00' };

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
