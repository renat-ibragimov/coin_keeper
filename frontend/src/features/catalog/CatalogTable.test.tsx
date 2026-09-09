import { fireEvent, render, screen } from '@testing-library/react';
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

function renderTable(items: CatalogListItem[], update = vi.fn(), params = '') {
  render(
    <MemoryRouter>
      <CatalogTable
        items={items}
        filters={parseFilters(new URLSearchParams(params))}
        update={update}
      />
    </MemoryRouter>,
  );
  return update;
}

describe('CatalogTable', () => {
  it('marks an owned row with the accessible icon and tints it, plain otherwise', () => {
    renderTable([
      makeItem({ id: 1, title: 'Missing', quantityOwned: 0 }),
      makeItem({ id: 2, title: 'Owned', quantityOwned: 3 }),
    ]);

    expect(screen.getByLabelText('У моїй колекції')).toBeInTheDocument();
    const rows = document.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows[0]?.className ?? '').not.toMatch(/_ownedRow_/);
    expect(rows[1]?.className ?? '').toMatch(/_ownedRow_/);
  });

  it('sorts by every column it shows, the material one included', () => {
    const update = renderTable([makeItem()]);
    fireEvent.click(screen.getByRole('button', { name: /Матеріал/ }));
    expect(update).toHaveBeenCalledWith({ sort: 'material', order: 'asc' });

    // The column that already sorts the listing flips instead.
    const flip = renderTable([makeItem()], vi.fn(), 'sort=material&order=asc');
    fireEvent.click(screen.getAllByRole('button', { name: /Матеріал/ })[1]!);
    expect(flip).toHaveBeenCalledWith({ sort: 'material', order: 'desc' });
  });

  it('shows the composition name, falling back to the free-text material', () => {
    renderTable([
      makeItem({
        id: 1,
        composition: { id: 3, code: 'silver', name: 'Срібло' },
        material: 'Latten',
      }),
      makeItem({ id: 2, composition: null, material: 'Нейзильбер' }),
      makeItem({ id: 3, composition: null, material: null }),
    ]);

    expect(screen.getByText('Срібло')).toBeInTheDocument();
    expect(screen.queryByText('Latten')).not.toBeInTheDocument();
    expect(screen.getByText('Нейзильбер')).toBeInTheDocument();
  });
});
