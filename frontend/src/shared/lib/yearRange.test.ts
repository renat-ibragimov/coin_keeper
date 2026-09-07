import { describe, expect, it } from 'vitest';

import type { CountryOut } from '@/shared/api/types';

import { buildYearList, clampYear, computeYearBounds } from './yearRange';

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

describe('computeYearBounds', () => {
  it("uses the selected country's own bounds when it has any coins", () => {
    const countries = [
      country({ id: 1, minYear: 1995, maxYear: 2024 }),
      country({ id: 2, minYear: 1900, maxYear: 2020 }),
    ];
    expect(computeYearBounds(countries, 1)).toEqual({ min: 1995, max: 2024 });
  });

  it('spans every country in the list when none is selected', () => {
    const countries = [
      country({ id: 1, minYear: 1995, maxYear: 2010 }),
      country({ id: 2, minYear: 1980, maxYear: 2024 }),
    ];
    expect(computeYearBounds(countries, undefined)).toEqual({ min: 1980, max: 2024 });
  });

  it('skips countries with no coins when spanning the whole list', () => {
    const countries = [
      country({ id: 1, minYear: null, maxYear: null }),
      country({ id: 2, minYear: 2000, maxYear: 2005 }),
    ];
    expect(computeYearBounds(countries, undefined)).toEqual({ min: 2000, max: 2005 });
  });

  it('falls back to the selected country having no coins at all by using the whole list', () => {
    const countries = [
      country({ id: 1, minYear: null, maxYear: null }),
      country({ id: 2, minYear: 2000, maxYear: 2005 }),
    ];
    expect(computeYearBounds(countries, 1)).toEqual({ min: 2000, max: 2005 });
  });

  it('falls back to 1900..this year when the directory has no bounds at all', () => {
    expect(computeYearBounds([], undefined)).toEqual({ min: 1900, max: new Date().getFullYear() });
    expect(computeYearBounds([country({ minYear: null, maxYear: null })], undefined)).toEqual({
      min: 1900,
      max: new Date().getFullYear(),
    });
  });
});

describe('buildYearList', () => {
  it('lists every year in the range, oldest first', () => {
    expect(buildYearList({ min: 2018, max: 2021 })).toEqual([2018, 2019, 2020, 2021]);
  });

  it('returns a single year for a single-year range', () => {
    expect(buildYearList({ min: 2020, max: 2020 })).toEqual([2020]);
  });
});

describe('clampYear', () => {
  const bounds = { min: 1995, max: 2024 };

  it('leaves an in-range value untouched', () => {
    expect(clampYear(2010, bounds)).toBe(2010);
  });

  it('pulls a too-low value up to the minimum', () => {
    expect(clampYear(1900, bounds)).toBe(1995);
  });

  it('pulls a too-high value down to the maximum', () => {
    expect(clampYear(2099, bounds)).toBe(2024);
  });

  it('leaves an unset filter unset', () => {
    expect(clampYear(undefined, bounds)).toBeUndefined();
  });
});
