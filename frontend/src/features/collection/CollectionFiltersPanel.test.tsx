import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CountryOut } from '@/shared/api/types';

import { CollectionFiltersPanel } from './CollectionFiltersPanel';
import { parseCollectionFilters } from './useCollectionFilters';

function country(overrides: Partial<CountryOut>): CountryOut {
  return {
    id: 1,
    code: null,
    name: 'Test',
    nameOriginal: 'Test',
    originalLang: 'en',
    nameUk: null,
    nameEn: 'Test',
    collectVariants: false,
    isActive: true,
    sortOrder: 0,
    minYear: null,
    maxYear: null,
    ...overrides,
  };
}

const COUNTRIES: CountryOut[] = [
  country({ id: 1, code: 'UA', name: 'Україна', minYear: 1996, maxYear: 2018 }),
  country({ id: 2, code: 'US', name: 'США', minYear: 1900, maxYear: 2009 }),
];

function renderPanel(
  overrides: Partial<ReturnType<typeof parseCollectionFilters>> = {},
  update = vi.fn(),
) {
  const filters = { ...parseCollectionFilters(new URLSearchParams()), ...overrides };
  render(
    <CollectionFiltersPanel
      filters={filters}
      update={update}
      reset={vi.fn()}
      countries={COUNTRIES}
      series={[]}
      seriesLoading={false}
      denominations={[]}
      activeFilters={[]}
    />,
  );
  return update;
}

describe('CollectionFiltersPanel year fields', () => {
  it('clamps out-of-range years to the newly selected country instead of clearing them', () => {
    const update = renderPanel({ yearFrom: 1950, yearTo: 2025 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryId: 1, yearFrom: 1996, yearTo: 2018 }),
    );
  });

  it('trims "до" options to years no earlier than the chosen "від"', () => {
    renderPanel({ countryId: 1, yearFrom: 2010 });
    fireEvent.click(screen.getByLabelText('до'));
    expect(screen.queryByRole('option', { name: '2005' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2018' })).toBeInTheDocument();
  });
});
