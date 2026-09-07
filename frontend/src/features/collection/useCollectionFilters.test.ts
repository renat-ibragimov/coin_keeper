import { describe, expect, it } from 'vitest';

import {
  hasActiveFilters,
  parseCollectionFilters,
  serializeCollectionFilters,
} from './useCollectionFilters';

describe('collection filters', () => {
  it('defaults to newest purchases first in the card view', () => {
    expect(parseCollectionFilters(new URLSearchParams())).toEqual({
      q: '',
      countryId: undefined,
      seriesId: undefined,
      yearFrom: undefined,
      yearTo: undefined,
      denominationId: undefined,
      group: undefined,
      metalKind: undefined,
      grade: undefined,
      sort: 'date',
      order: 'desc',
      page: 1,
      view: 'cards',
    });
  });

  it('round-trips a full filter set through the URL', () => {
    const params = new URLSearchParams(
      'q=owl&countryId=1&seriesId=3&yearFrom=2010&yearTo=2020&denominationId=5' +
        '&group=commemorative&metalKind=base&grade=UNC&sort=total&order=asc&page=2&view=table',
    );
    const filters = parseCollectionFilters(params);
    expect(filters).toMatchObject({
      q: 'owl',
      countryId: 1,
      seriesId: 3,
      yearFrom: 2010,
      yearTo: 2020,
      denominationId: 5,
      group: 'commemorative',
      metalKind: 'base',
      grade: 'UNC',
      sort: 'total',
      order: 'asc',
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
      new URLSearchParams('sort=price&countryId=abc&group=bogus&metalKind=bogus&page=0'),
    );
    expect(filters.sort).toBe('date');
    expect(filters.countryId).toBeUndefined();
    expect(filters.group).toBeUndefined();
    expect(filters.metalKind).toBeUndefined();
    expect(filters.page).toBe(1);
  });

  it('knows whether anything narrows the listing', () => {
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('view=table')))).toBe(
      false,
    );
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('seriesId=2')))).toBe(true);
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('grade=UNC')))).toBe(true);
  });
});
