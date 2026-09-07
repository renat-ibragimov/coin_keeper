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

describe('CollectionFiltersPanel year fields', () => {
  it('clamps out-of-range years to the newly selected country instead of clearing them', () => {
    const { update } = renderPanel({ yearFrom: 1950, yearTo: 2025 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryId: 1, yearFrom: 1996, yearTo: 2018 }),
    );
  });

  it('suggests "до" years no earlier than the chosen "від", oldest first', () => {
    renderPanel({ countryId: 1, yearFrom: 2010 });
    const values = suggestedYears('до');
    expect(values).not.toContain('2005');
    expect(values[0]).toBe('2010');
    expect(values[values.length - 1]).toBe('2018');
  });
});
