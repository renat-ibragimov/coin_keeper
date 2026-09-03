import { describe, expect, it } from 'vitest';

import { formatDate, formatMoney, formatSignedPercent, formatSignedUah, formatUah } from './format';

describe('format helpers', () => {
  it('formats hryvnia amounts from API strings', () => {
    expect(formatUah('42765.66', 'en')).toBe('42,765.66 ₴');
    expect(formatUah(null, 'uk')).toBeNull();
    expect(formatUah('not a number', 'uk')).toBeNull();
  });

  it('spells out the sign of a delta', () => {
    expect(formatSignedUah(1234, 'en')).toBe('+1,234 ₴');
    expect(formatSignedUah(-1234, 'en')).toBe('−1,234 ₴');
    expect(formatSignedUah(0, 'en')).toBe('0 ₴');
    expect(formatSignedPercent(12.34, 'en')).toBe('+12.3 %');
    expect(formatSignedPercent(-3, 'en')).toBe('−3 %');
    expect(formatSignedPercent(null, 'en')).toBeNull();
  });

  it('formats foreign purchase prices with their symbol', () => {
    expect(formatMoney('12.5', 'USD', 'en')).toBe('12.5 $');
    expect(formatMoney('10', 'eur', 'en')).toBe('10 €');
    expect(formatMoney('99', 'PLN', 'en')).toBe('99 PLN');
    expect(formatMoney(null, 'USD', 'en')).toBeNull();
  });

  it('formats calendar dates and timestamps', () => {
    expect(formatDate('2025-04-02', 'uk')).toBe('02.04.2025');
    expect(formatDate('2025-04-02T10:00:00Z', 'en')).toBe('02/04/2025');
    expect(formatDate(null, 'en')).toBeNull();
  });
});
