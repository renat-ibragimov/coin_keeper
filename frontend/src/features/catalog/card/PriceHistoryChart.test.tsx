import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';
import type { PriceHistoryItem } from '@/shared/api/types';

import { toChartPoints } from './chartData';
import { PriceHistoryChart } from './PriceHistoryChart';

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

const HISTORY: PriceHistoryItem[] = [
  snapshot({ id: 3, observedAt: '2024-03-10T00:00:00Z', priceUah: '650.00' }),
  snapshot({ id: 2, observedAt: '2024-02-10T00:00:00Z', priceUah: '99999.00', isSuspect: true }),
  snapshot({ id: 1, observedAt: '2024-01-10T00:00:00Z', priceUah: '500.00' }),
  snapshot({ id: 4, observedAt: '2024-04-01T00:00:00Z', priceUah: '700.00', isOwn: true }),
];

describe('PriceHistoryChart', () => {
  it('orders points by time and drops the unplottable ones', () => {
    const points = toChartPoints([
      ...HISTORY,
      snapshot({ id: 5, currencyCode: 'USD', priceUah: null }),
    ]);
    expect(points.map((point) => point.source.id)).toEqual([1, 2, 3, 4]);
  });

  it('keeps suspect snapshots out of the trend line but marks them', () => {
    render(<PriceHistoryChart items={HISTORY} />);

    expect(screen.getAllByTestId('suspect-point')).toHaveLength(1);
    expect(screen.getAllByTestId('point')).toHaveLength(2);
    expect(screen.getAllByTestId('own-point')).toHaveLength(1);
    // three trend points → two segments, the suspect one never joined
    const line = screen.getByTestId('trend-line').getAttribute('d') ?? '';
    expect(line.split('L')).toHaveLength(3);
    expect(screen.getByText('підозріла ціна')).toBeInTheDocument();
  });

  it('says there are no prices for an empty history', () => {
    render(<PriceHistoryChart items={[]} />);
    expect(screen.getByText('Цін ще немає.')).toBeInTheDocument();
  });
});
