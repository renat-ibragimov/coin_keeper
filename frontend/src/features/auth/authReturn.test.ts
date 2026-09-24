import { describe, expect, it } from 'vitest';
import { guestDestination, safeAuthReturn } from './authReturn';

describe('authentication destinations', () => {
  it.each([
    'https://example.test',
    '//example.test',
    '/\\example.test',
    '/login',
    '/login/',
    '/reset-password?token=secret',
  ])('rejects unsafe or recursive return paths: %s', (path) => {
    expect(safeAuthReturn(path)).toBeNull();
  });
  it('preserves the selected item, filters and anchor', () => {
    expect(safeAuthReturn('/collection/add?catalogItemId=7#purchase')).toBe(
      '/collection/add?catalogItemId=7#purchase',
    );
  });
  it.each([
    ['/settings', '/'],
    ['/settings/', '/'],
    ['/admin', '/'],
    ['/collection/add?catalogItemId=7', '/collection/coins'],
    ['/collection/coins/7/edit', '/collection/coins'],
    ['/collection/completeness/series/3', '/collection/completeness'],
    ['/collection/money?category=delivery', '/collection/money?category=delivery'],
    ['/catalog/7?tab=prices', '/catalog/7?tab=prices'],
  ])('returns %s to its public counterpart', (path, expected) => {
    expect(guestDestination(path)).toBe(expected);
  });
});
