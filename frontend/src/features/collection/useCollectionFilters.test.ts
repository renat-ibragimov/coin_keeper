import { describe, expect, it } from 'vitest';

import {
  hasActiveFilters,
  parseCollectionFilters,
  serializeCollectionFilters,
} from './useCollectionFilters';

describe('collection filters', () => {
  it('defaults to alphabetical order by title in the card view', () => {
    expect(parseCollectionFilters(new URLSearchParams())).toEqual({
      q: '',
      countryIds: [],
      seriesIds: [],
      yearFrom: undefined,
      yearTo: undefined,
      denominationIds: [],
      groups: [],
      materialIds: [],
      grade: undefined,
      sort: 'title',
      order: 'asc',
      page: 1,
      view: 'cards',
    });
  });

  it('round-trips a full filter set, including repeated multi-select keys', () => {
    const params = new URLSearchParams(
      'q=owl&countryId=1&countryId=2&seriesId=3&yearFrom=2010&yearTo=2020&denominationId=5' +
        '&group=commemorative&group=other&materialId=7&materialId=8&grade=UNC' +
        '&sort=total&order=desc&page=2&view=table',
    );
    const filters = parseCollectionFilters(params);
    expect(filters).toMatchObject({
      q: 'owl',
      countryIds: [1, 2],
      seriesIds: [3],
      yearFrom: 2010,
      yearTo: 2020,
      denominationIds: [5],
      groups: ['commemorative', 'other'],
      materialIds: [7, 8],
      grade: 'UNC',
      sort: 'total',
      order: 'desc',
      page: 2,
      view: 'table',
    });
    expect(serializeCollectionFilters(filters).toString()).toBe(params.toString());
    expect(
      serializeCollectionFilters(parseCollectionFilters(new URLSearchParams())).toString(),
    ).toBe('');
  });

  it('ignores unknown sorts, groups and malformed ids', () => {
    const filters = parseCollectionFilters(
      new URLSearchParams('sort=price&countryId=abc&group=bogus&materialId=abc&page=0'),
    );
    expect(filters.sort).toBe('title');
    expect(filters.countryIds).toEqual([]);
    expect(filters.groups).toEqual([]);
    expect(filters.materialIds).toEqual([]);
    expect(filters.page).toBe(1);
  });

  it('de-duplicates a repeated value', () => {
    const filters = parseCollectionFilters(new URLSearchParams('countryId=1&countryId=1'));
    expect(filters.countryIds).toEqual([1]);
  });

  it('knows whether anything narrows the listing', () => {
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('view=table')))).toBe(false);
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('seriesId=2')))).toBe(true);
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('grade=UNC')))).toBe(true);
  });
});
