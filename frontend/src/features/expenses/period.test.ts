import { describe, expect, it } from 'vitest';

import { presetRange } from './period';

describe('presetRange', () => {
  const today = new Date(2026, 8, 13); // 13 September 2026 (months are 0-indexed)

  it('goes back one, three, six or twelve months from today', () => {
    expect(presetRange('1m', today)).toEqual({ dateFrom: '2026-08-13', dateTo: '2026-09-13' });
    expect(presetRange('3m', today)).toEqual({ dateFrom: '2026-06-13', dateTo: '2026-09-13' });
    expect(presetRange('6m', today)).toEqual({ dateFrom: '2026-03-13', dateTo: '2026-09-13' });
    expect(presetRange('1y', today)).toEqual({ dateFrom: '2025-09-13', dateTo: '2026-09-13' });
  });

  it('clamps to the last day of a shorter target month', () => {
    const endOfMarch = new Date(2026, 2, 31); // 31 March 2026
    expect(presetRange('1m', endOfMarch).dateFrom).toBe('2026-02-28');
  });
});
