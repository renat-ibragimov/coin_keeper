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
  return { update };
}

/** The suggestion years listed in a year field's dropdown, opened by focusing it. */
function suggestedYears(fieldLabel: string): string[] {
  const input = screen.getByLabelText(fieldLabel);
  fireEvent.focus(input);
  const listboxId = input.getAttribute('aria-controls');
  const listbox = listboxId ? document.getElementById(listboxId) : null;
  return Array.from(listbox?.querySelectorAll('[role="option"]') ?? []).map(
    (option) => option.textContent ?? '',
  );
}

describe('FiltersPanel year fields', () => {
  it('clamps out-of-range years to the newly selected country instead of clearing them', () => {
    const { update } = renderPanel({ yearFrom: 1980, yearTo: 2030 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryId: 1, yearFrom: 1995, yearTo: 2024 }),
    );
  });

  it('leaves in-range years untouched when the country changes', () => {
    const { update } = renderPanel({ yearFrom: 2000, yearTo: 2010 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryId: 1, yearFrom: 2000, yearTo: 2010 }),
    );
  });

  it('accepts a typed year outside the suggested list', () => {
    const { update } = renderPanel({ countryId: 1 });
    fireEvent.change(screen.getByLabelText('від'), { target: { value: '2003' } });
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ yearFrom: 2003 }));
  });

  it('suggests "до" years no earlier than the chosen "від", oldest first', () => {
    renderPanel({ countryId: 1, yearFrom: 2015 });
    const values = suggestedYears('до');
    expect(values).not.toContain('2010');
    expect(values.slice(0, 3)).toEqual(['2015', '2016', '2017']);
    expect(values[values.length - 1]).toBe('2024');
  });

  it('suggests "від" years no later than the chosen "до", oldest first', () => {
    renderPanel({ countryId: 1, yearTo: 2000 });
    const values = suggestedYears('від');
    expect(values).not.toContain('2005');
    expect(values[0]).toBe('1995');
    expect(values[values.length - 1]).toBe('2000');
  });

  it('picks a suggested year from the dropdown', () => {
    const { update } = renderPanel({ countryId: 1 });
    fireEvent.focus(screen.getByLabelText('від'));
    fireEvent.click(screen.getByRole('option', { name: '1995' }));
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ yearFrom: 1995 }));
  });
});
