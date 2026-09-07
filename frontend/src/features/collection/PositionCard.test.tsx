import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';
import type { CollectionPosition } from '@/shared/api/types';

import { PositionCard } from './PositionCard';

const BASE: CollectionPosition = {
  catalogItemId: 7,
  title: 'Дельфін',
  country: 'Україна',
  seriesName: 'Флора і фауна',
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
  return render(
    <MemoryRouter>
      <PositionCard item={item} />
    </MemoryRouter>,
  );
}

describe('PositionCard', () => {
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

  it('links the whole title and the "add another" action to the right places', () => {
    renderCard(BASE);
    expect(screen.getByRole('link', { name: 'Дельфін' })).toHaveAttribute('href', '/catalog/7');
    expect(screen.getByRole('link', { name: /Додати ще екземпляр/ })).toHaveAttribute(
      'href',
      '/collection/coins/new?catalogItemId=7',
    );
  });
});
