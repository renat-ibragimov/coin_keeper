import { describe, expect, it } from 'vitest';

import { isRecentRelease } from './recentRelease';

const NOW = new Date('2026-09-21T18:00:00Z');

describe('isRecentRelease', () => {
  it('includes today and the full 30-day boundary', () => {
    expect(isRecentRelease('2026-09-21', NOW)).toBe(true);
    expect(isRecentRelease('2026-08-22', NOW)).toBe(true);
  });

  it('excludes older, future, missing and invalid dates', () => {
    expect(isRecentRelease('2026-08-21', NOW)).toBe(false);
    expect(isRecentRelease('2026-09-22', NOW)).toBe(false);
    expect(isRecentRelease(null, NOW)).toBe(false);
    expect(isRecentRelease('not-a-date', NOW)).toBe(false);
  });
});
