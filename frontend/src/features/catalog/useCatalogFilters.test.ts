import { describe, expect, it } from 'vitest';

import { parseFilters, serializeFilters } from './useCatalogFilters';

describe('catalog filters ↔ URL', () => {
  it('parses defaults from an empty URL', () => {
    const filters = parseFilters(new URLSearchParams());
    expect(filters).toMatchObject({
      q: '',
      scope: 'all',
      archived: false,
      sort: 'country',
      order: 'asc',
      page: 1,
      view: 'cards',
    });
    expect(filters.countryId).toBeUndefined();
    expect(filters.owned).toBeUndefined();
  });

  it('round-trips a full filter set', () => {
    const params = new URLSearchParams(
      'q=dolphin&countryId=2&yearFrom=2010&yearTo=2020&denominationId=5' +
        '&group=commemorative&metalKind=base&owned=true&scope=own&archived=true' +
        '&sort=price&order=desc&page=3&view=table',
    );
    const filters = parseFilters(params);
    expect(filters).toMatchObject({
      q: 'dolphin',
      countryId: 2,
      yearFrom: 2010,
      yearTo: 2020,
      denominationId: 5,
      group: 'commemorative',
      metalKind: 'base',
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
    expect(filters.countryId).toBeUndefined();
    expect(filters.group).toBeUndefined();
    expect(filters.sort).toBe('country');
    expect(filters.page).toBe(1);
    expect(filters.owned).toBeUndefined();
  });
});
