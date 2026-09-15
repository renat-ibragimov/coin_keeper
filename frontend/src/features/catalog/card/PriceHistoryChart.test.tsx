import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { PriceHistoryItem } from '@/shared/api/types';
import { ThemeContext } from '@/shared/theme/themeContext';

import { PriceHistoryChart } from './PriceHistoryChart';

const mocks = vi.hoisted(() => {
  const timeScale = { fitContent: vi.fn(), setVisibleRange: vi.fn() };
  const series = { setData: vi.fn() };
  const chart = {
    addSeries: vi.fn(() => series),
    timeScale: vi.fn(() => timeScale),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    remove: vi.fn(),
  };
  return {
    createChart: vi.fn(() => chart),
    createSeriesMarkers: vi.fn((_series: unknown, markers: { id?: string }[]) => {
      void markers;
      return { setMarkers: vi.fn() };
    }),
    chart,
    series,
    timeScale,
  };
});

vi.mock('lightweight-charts', () => ({
  createChart: mocks.createChart,
  createSeriesMarkers: mocks.createSeriesMarkers,
  AreaSeries: 'Area',
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Magnet: 1 },
  LineStyle: { Dotted: 2, Solid: 0 },
}));

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
  snapshot({ id: 1, observedAt: '2024-01-10T00:00:00Z', priceUah: '500.00' }),
  snapshot({ id: 2, observedAt: '2024-02-10T00:00:00Z', priceUah: '99999.00', isSuspect: true }),
  snapshot({ id: 3, observedAt: '2024-03-10T00:00:00Z', priceUah: '650.00' }),
  snapshot({ id: 4, observedAt: '2024-04-01T00:00:00Z', priceUah: '700.00', isOwn: true }),
];

function renderChart(items: PriceHistoryItem[]) {
  return render(
    <ThemeContext.Provider value={{ theme: 'light', preference: 'light', setPreference: () => {} }}>
      <PriceHistoryChart items={items} />
    </ThemeContext.Provider>,
  );
}

describe('PriceHistoryChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('says there are no prices for an empty history, without creating a chart', () => {
    renderChart([]);
    expect(screen.getByText('Цін ще немає.')).toBeInTheDocument();
    expect(mocks.createChart).not.toHaveBeenCalled();
  });

  it('plots the non-suspect points and markers the own and suspect ones', () => {
    renderChart(HISTORY);

    expect(mocks.createChart).toHaveBeenCalledTimes(1);
    expect(mocks.series.setData).toHaveBeenCalledWith([
      { time: expect.any(Number), value: 500 },
      { time: expect.any(Number), value: 650 },
      { time: expect.any(Number), value: 700 },
    ]);
    const markers = mocks.createSeriesMarkers.mock.calls[0]![1];
    expect(markers.map((marker) => marker.id).sort()).toEqual(['2', '4']);
    expect(mocks.timeScale.fitContent).toHaveBeenCalledTimes(1);
  });

  it('offers quick range buttons that move the visible range', () => {
    renderChart(HISTORY);

    fireEvent.click(screen.getByRole('tab', { name: '1Р' }));
    expect(mocks.timeScale.setVisibleRange).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('tab', { name: 'Усі' }));
    expect(mocks.timeScale.fitContent).toHaveBeenCalledTimes(2);
  });

  it('tears the chart down on unmount', () => {
    const { unmount } = renderChart(HISTORY);
    unmount();
    expect(mocks.chart.remove).toHaveBeenCalledTimes(1);
  });
});
