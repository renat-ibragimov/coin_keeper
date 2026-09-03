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
      sort: 'date',
      order: 'desc',
      page: 1,
      view: 'cards',
    });
  });

  it('round-trips through the URL and drops defaults', () => {
    const params = new URLSearchParams(
      'q=owl&countryId=1&seriesId=3&sort=total&order=asc&page=2&view=list',
    );
    const filters = parseCollectionFilters(params);
    expect(filters).toMatchObject({
      q: 'owl',
      countryId: 1,
      seriesId: 3,
      sort: 'total',
      order: 'asc',
      page: 2,
      view: 'list',
    });
    expect(serializeCollectionFilters(filters).toString()).toBe(params.toString());
    expect(
      serializeCollectionFilters(parseCollectionFilters(new URLSearchParams())).toString(),
    ).toBe('');
  });

  it('ignores unknown sorts and malformed ids', () => {
    const filters = parseCollectionFilters(new URLSearchParams('sort=price&countryId=abc&page=0'));
    expect(filters.sort).toBe('date');
    expect(filters.countryId).toBeUndefined();
    expect(filters.page).toBe(1);
  });

  it('knows whether anything narrows the listing', () => {
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('view=list')))).toBe(false);
    expect(hasActiveFilters(parseCollectionFilters(new URLSearchParams('seriesId=2')))).toBe(true);
  });
});
