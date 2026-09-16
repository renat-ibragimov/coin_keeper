import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CollectionPosition } from '@/shared/api/types';

import { PositionCard } from './PositionCard';

const fetchCard = vi.fn();

vi.mock('@/features/catalog/api', () => ({
  fetchCard: (...args: unknown[]) => fetchCard(...args),
}));

const BASE: CollectionPosition = {
  catalogItemId: 7,
  title: 'Дельфін',
  country: 'Україна',
  seriesName: 'Флора і фауна',
  collectionGroup: 'commemorative',
  denomination: '2 ₴',
  year: 2018,
  isArchived: false,
  archiveReason: null,
  totalQuantity: 2,
  totalSpendUah: '1100.00',
  marketValueUah: '1600.00',
  lastAcquisitionDate: '2024-03-05',
  grades: [],
  thumbnailUrl: null,
};

function renderCard(item: CollectionPosition) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PositionCard item={item} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PositionCard', () => {
  beforeEach(() => {
    fetchCard.mockReturnValue(new Promise(() => undefined));
  });

  it('rolls up every purchase of the coin into one set of totals', () => {
    renderCard(BASE);
    expect(screen.getByText('2 шт.')).toBeInTheDocument();
    expect(screen.getByText('1 100 ₴')).toBeInTheDocument();
    expect(screen.getByText('1 600 ₴')).toBeInTheDocument();
    expect(screen.getByText('05.03.2024')).toBeInTheDocument();
  });

  it('shows a dash for the valuation and the last purchase date when absent', () => {
    renderCard({ ...BASE, marketValueUah: null, lastAcquisitionDate: null });
    expect(screen.getAllByText('—')).toHaveLength(1);
    expect(screen.getByText('Ціни немає')).toBeInTheDocument();
  });

  it('shows no grade badge when no purchase has one', () => {
    renderCard(BASE);
    expect(screen.queryByText('UNC')).toBeNull();
  });

  it('shows a single grade as-is', () => {
    renderCard({ ...BASE, grades: ['UNC'] });
    expect(screen.getByText('UNC')).toBeInTheDocument();
  });

  it('joins several distinct grades with a middle dot', () => {
    renderCard({ ...BASE, grades: ['UNC', 'XF'] });
    expect(screen.getByText('UNC · XF')).toBeInTheDocument();
  });

  it('shows the catalog obverse and reverse as an overlapping pair', async () => {
    fetchCard.mockResolvedValue({
      obverseImage: { preview: '/obverse-preview.webp', medium: '/obverse-medium.webp' },
      reverseImage: { preview: '/reverse-preview.webp', medium: '/reverse-medium.webp' },
    });

    const { container } = renderCard({ ...BASE, thumbnailUrl: '/fallback.webp' });
    const images = await waitFor(() => {
      const rendered = container.querySelectorAll('img');
      expect(rendered).toHaveLength(2);
      return rendered;
    });

    expect(images[0]).toHaveAttribute('src', '/obverse-preview.webp');
    expect(images[1]).toHaveAttribute('src', '/reverse-preview.webp');
  });

  it('links the whole title and the "add another" action to the right places', () => {
    renderCard(BASE);
    expect(screen.getByRole('link', { name: 'Дельфін' })).toHaveAttribute('href', '/catalog/7');
    expect(screen.getByRole('link', { name: /Додати ще екземпляр/ })).toHaveAttribute(
      'href',
      '/collection/add?catalogItemId=7',
    );
  });
});
