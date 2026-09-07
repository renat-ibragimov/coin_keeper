import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CatalogListItem } from '@/shared/api/types';

import { CatalogTable } from './CatalogTable';
import { parseFilters } from './useCatalogFilters';

function makeItem(overrides: Partial<CatalogListItem> = {}): CatalogListItem {
  return {
    id: 1,
    country: 'Ukraine',
    seriesName: null,
    denomination: null,
    year: 2021,
    title: 'Sikorsky',
    titleOriginal: 'Ihor Sikorsky',
    originalLang: 'uk',
    titleUk: null,
    titleUkSource: null,
    titleEn: null,
    titleEnSource: null,
    variety: null,
    catalogNumber: null,
    collectionGroup: 'commemorative',
    metalKind: 'base',
    composition: null,
    material: null,
    marketPriceUah: null,
    priceSource: null,
    priceObservedAt: null,
    quantityOwned: 0,
    purchaseTotalUah: '0.00',
    obverseImage: null,
    reverseImage: null,
    thumbnailUrl: null,
    isOwn: false,
    isArchived: false,
    archiveReason: null,
    sourceUrl: null,
    ...overrides,
  };
}

function renderTable(items: CatalogListItem[]) {
  return render(
    <MemoryRouter>
      <CatalogTable items={items} filters={parseFilters(new URLSearchParams())} update={vi.fn()} />
    </MemoryRouter>,
  );
}

describe('CatalogTable', () => {
  it('marks an owned row with the accessible icon and tints it, plain otherwise', () => {
    const { container } = renderTable([
      makeItem({ id: 1, title: 'Missing', quantityOwned: 0 }),
      makeItem({ id: 2, title: 'Owned', quantityOwned: 3 }),
    ]);

    expect(screen.getByLabelText('У моїй колекції')).toBeInTheDocument();
    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows[0]?.className ?? '').not.toMatch(/_ownedRow_/);
    expect(rows[1]?.className ?? '').toMatch(/_ownedRow_/);
  });
});
