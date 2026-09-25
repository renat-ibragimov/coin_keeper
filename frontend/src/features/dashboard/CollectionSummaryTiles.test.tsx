import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';

import { CollectionSummaryTiles, type CollectionSummaryTilesData } from './CollectionSummaryTiles';

const DATA: CollectionSummaryTilesData = {
  collectionItems: 3,
  completedItems: 2,
  coinSpendUah: '100.00',
  relatedSpendUah: '30.00',
  totalSpendUah: '130.00',
  marketValueUah: '200.00',
};

function renderTiles(includeSupportingExpenses?: boolean) {
  return render(
    <MemoryRouter>
      <CollectionSummaryTiles data={DATA} includeSupportingExpenses={includeSupportingExpenses} />
    </MemoryRouter>,
  );
}

describe('CollectionSummaryTiles', () => {
  it('counts supporting expenses in the spend and the difference by default', () => {
    renderTiles();
    expect(screen.getByText('130 ₴')).toBeInTheDocument();
    expect(screen.getByText('у т. ч. супутні витрати: 30 ₴')).toBeInTheDocument();
    expect(screen.getByText('+70 ₴')).toBeInTheDocument();
  });

  it('leaves supporting expenses out of the spend and the difference when the setting is off', () => {
    renderTiles(false);
    expect(screen.getByText('100 ₴')).toBeInTheDocument();
    expect(screen.queryByText(/супутні витрати/)).toBeNull();
    expect(screen.getByText('+100 ₴')).toBeInTheDocument();
  });
});
