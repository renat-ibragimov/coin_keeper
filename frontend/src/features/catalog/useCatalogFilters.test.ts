import { describe, expect, it } from 'vitest';

import { parseFilters, serializeFilters } from './useCatalogFilters';

describe('catalog filters ↔ URL', () => {
  it('parses defaults from an empty URL', () => {
    const filters = parseFilters(new URLSearchParams());
    expect(filters).toMatchObject({
      q: '',
      countryIds: [],
      seriesIds: [],
      denominationIds: [],
      groups: [],
      materialIds: [],
      scope: 'all',
      archived: false,
      sort: 'title',
      order: 'asc',
      page: 1,
      view: 'cards',
    });
    expect(filters.owned).toBeUndefined();
  });

  it('round-trips a full filter set, including repeated multi-select keys', () => {
    const params = new URLSearchParams(
      'q=dolphin&countryId=2&countryId=3&yearFrom=2010&yearTo=2020&denominationId=5' +
        '&group=commemorative&group=other&materialId=7&materialId=8&owned=true&scope=own' +
        '&archived=true&sort=price&order=desc&page=3&view=table',
    );
    const filters = parseFilters(params);
    expect(filters).toMatchObject({
      q: 'dolphin',
      countryIds: [2, 3],
      yearFrom: 2010,
      yearTo: 2020,
      denominationIds: [5],
      groups: ['commemorative', 'other'],
      materialIds: [7, 8],
      owned: true,
      scope: 'own',
      archived: true,
      sort: 'price',
      order: 'desc',
      page: 3,
      view: 'table',
    });

    const back = serializeFilters(filters);
    expect(parseFilters(back)).toEqual(filters);
  });

  it('drops defaults from the URL', () => {
    const filters = parseFilters(new URLSearchParams());
    expect(serializeFilters(filters).toString()).toBe('');
  });

  it('ignores garbage values', () => {
    const params = new URLSearchParams('countryId=abc&group=bogus&sort=hack&page=-1&owned=maybe');
    const filters = parseFilters(params);
    expect(filters.countryIds).toEqual([]);
    expect(filters.groups).toEqual([]);
    expect(filters.sort).toBe('title');
    expect(filters.page).toBe(1);
    expect(filters.owned).toBeUndefined();
  });

  it('de-duplicates a repeated value', () => {
    const filters = parseFilters(new URLSearchParams('countryId=1&countryId=1'));
    expect(filters.countryIds).toEqual([1]);
  });

  it('degrades a stale ?view=map to cards', () => {
    const filters = parseFilters(new URLSearchParams('view=map'));
    expect(filters.view).toBe('cards');
  });
});
