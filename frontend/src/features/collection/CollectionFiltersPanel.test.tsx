import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CoinMaterial, CountryOut } from '@/shared/api/types';

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

const MATERIALS: CoinMaterial[] = [
  { id: 1, code: 'silver', name: 'Срібло' },
  { id: 2, code: 'gold', name: 'Золото' },
];

function renderPanel(
  overrides: Partial<ReturnType<typeof parseCollectionFilters>> = {},
  update = vi.fn(),
  materials: CoinMaterial[] = [],
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
      materials={materials}
      activeFilters={[]}
    />,
  );
  return { update };
}

/** A stateful wrapper so a second click sees the first click's own change —
 *  needed for multi-select, where each toggle must build on the last one
 *  instead of every click starting fresh from the initial props. */
function renderControlledPanel(materials: CoinMaterial[] = []) {
  const onChange = vi.fn();
  function Controlled() {
    const [filters, setFilters] = useState(parseCollectionFilters(new URLSearchParams()));
    return (
      <CollectionFiltersPanel
        filters={filters}
        update={(changes) => {
          onChange(changes);
          setFilters((current) => ({ ...current, ...changes }));
        }}
        reset={vi.fn()}
        countries={COUNTRIES}
        series={[]}
        seriesLoading={false}
        denominations={[]}
        materials={materials}
        activeFilters={[]}
      />
    );
  }
  render(<Controlled />);
  return { onChange };
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

describe('CollectionFiltersPanel multi-select', () => {
  it('picks more than one country without closing the menu', () => {
    const { onChange } = renderControlledPanel();
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));
    fireEvent.click(screen.getByRole('option', { name: 'США' }));

    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ countryIds: [1, 2] }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('resets series, denomination and material when the country selection changes', () => {
    const { update } = renderPanel({
      countryIds: [1],
      seriesIds: [10],
      denominationIds: [20],
      materialIds: [30],
    });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'США' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        countryIds: [1, 2],
        seriesIds: [],
        denominationIds: [],
        materialIds: [],
      }),
    );
  });

  it('offers the materials it was given and multi-selects them', () => {
    const { onChange } = renderControlledPanel(MATERIALS);
    fireEvent.click(screen.getByLabelText('Метал'));
    fireEvent.click(screen.getByRole('option', { name: 'Срібло' }));
    fireEvent.click(screen.getByRole('option', { name: 'Золото' }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ materialIds: [1, 2] }));
  });
});

describe('CollectionFiltersPanel year fields', () => {
  it('clamps out-of-range years to the newly selected country instead of clearing them', () => {
    const { update } = renderPanel({ yearFrom: 1950, yearTo: 2025 });
    fireEvent.click(screen.getByLabelText('Країна'));
    fireEvent.click(screen.getByRole('option', { name: 'Україна' }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ countryIds: [1], yearFrom: 1996, yearTo: 2018 }),
    );
  });

  it('suggests "до" years no earlier than the chosen "від", oldest first', () => {
    renderPanel({ countryIds: [1], yearFrom: 2010 });
    const values = suggestedYears('до');
    expect(values).not.toContain('2005');
    expect(values[0]).toBe('2010');
    expect(values[values.length - 1]).toBe('2018');
  });
});
