import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CountryOut } from '@/shared/api/types';

import { FiltersPanel } from './FiltersPanel';
import { parseFilters } from './useCatalogFilters';

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
  country({ id: 1, code: 'UA', name: 'Україна', minYear: 1995, maxYear: 2024 }),
  country({ id: 2, code: 'US', name: 'США', minYear: 1900, maxYear: 2020 }),
];

function renderPanel(overrides: Partial<ReturnType<typeof parseFilters>> = {}, update = vi.fn()) {
  const filters = { ...parseFilters(new URLSearchParams()), ...overrides };
  render(
    <FiltersPanel
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

describe('FiltersPanel year fields', () => {
  it('clamps out-of-range years to the newly selected country instead of clearing them', () => {
    const update = renderPanel({ yearFrom: 1980, yearTo: 2030 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryId: 1, yearFrom: 1995, yearTo: 2024 }),
    );
  });

  it('leaves in-range years untouched when the country changes', () => {
    const update = renderPanel({ yearFrom: 2000, yearTo: 2010 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryId: 1, yearFrom: 2000, yearTo: 2010 }),
    );
  });

  it('trims "до" options to years no earlier than the chosen "від"', () => {
    renderPanel({ countryId: 1, yearFrom: 2015 });
    fireEvent.click(screen.getByLabelText('до'));
    expect(screen.queryByRole('option', { name: '2010' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2015' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2024' })).toBeInTheDocument();
  });

  it('trims "від" options to years no later than the chosen "до"', () => {
    renderPanel({ countryId: 1, yearTo: 2000 });
    fireEvent.click(screen.getByLabelText('від'));
    expect(screen.queryByRole('option', { name: '2005' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2000' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '1995' })).toBeInTheDocument();
  });
});
