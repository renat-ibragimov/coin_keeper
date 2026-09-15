import { describe, expect, it } from 'vitest';

import type { PriceHistoryItem } from '@/shared/api/types';

import { toChartPoints } from './chartData';
import { buildPriceSeries, rangeStart } from './priceChartData';

function snapshot(overrides: Partial<PriceHistoryItem>): PriceHistoryItem {
  return {
    id: 1,
    source: 'ua-coins',
    grade: 'UNC',
    price: '500.00',
    currencyCode: 'UAH',
    priceUah: '500.00',
    observedAt: '2024-01-10T00:00:00Z',
    sourceUrl: null,
    isOwn: false,
    isSuspect: false,
    ...overrides,
  };
}

describe('buildPriceSeries', () => {
  it('keeps suspect snapshots out of the series but marks them', () => {
    const points = toChartPoints([
      snapshot({ id: 1, observedAt: '2024-01-10T00:00:00Z', priceUah: '500.00' }),
      snapshot({
        id: 2,
        observedAt: '2024-02-10T00:00:00Z',
        priceUah: '99999.00',
        isSuspect: true,
      }),
      snapshot({ id: 3, observedAt: '2024-03-10T00:00:00Z', priceUah: '650.00' }),
      snapshot({ id: 4, observedAt: '2024-04-01T00:00:00Z', priceUah: '700.00', isOwn: true }),
    ]);
    const { series, markers } = buildPriceSeries(points);

    expect(series.map((point) => point.sourceId)).toEqual([1, 3, 4]);
    expect(markers).toEqual([
      { sourceId: 2, time: expect.any(Number), value: 99999, kind: 'suspect' },
      { sourceId: 4, time: expect.any(Number), value: 700, kind: 'own' },
    ]);
  });

  it('nudges a duplicate timestamp forward instead of dropping it', () => {
    const points = toChartPoints([
      snapshot({ id: 1, observedAt: '2024-01-10T00:00:00Z', priceUah: '500.00' }),
      snapshot({ id: 2, observedAt: '2024-01-10T00:00:00Z', priceUah: '520.00' }),
    ]);
    const { series } = buildPriceSeries(points);

    expect(series).toHaveLength(2);
    expect(series[1]!.time).toBe(series[0]!.time + 1);
  });

  it('returns an empty series and no markers for no history', () => {
    expect(buildPriceSeries([])).toEqual({ series: [], markers: [] });
  });
});

describe('rangeStart', () => {
  const latest = Math.floor(new Date('2026-09-13T00:00:00Z').getTime() / 1000);

  it('goes back one month, six months or a year from the latest point', () => {
    expect(new Date(rangeStart(latest, '1m') * 1000).toISOString()).toBe(
      '2026-08-13T00:00:00.000Z',
    );
    expect(new Date(rangeStart(latest, '6m') * 1000).toISOString()).toBe(
      '2026-03-13T00:00:00.000Z',
    );
    expect(new Date(rangeStart(latest, '1y') * 1000).toISOString()).toBe(
      '2025-09-13T00:00:00.000Z',
    );
  });

  it('has no lower bound for "all"', () => {
    expect(rangeStart(latest, 'all')).toBe(Number.NEGATIVE_INFINITY);
  });
});
