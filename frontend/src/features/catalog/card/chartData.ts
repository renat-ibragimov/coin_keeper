import type { PriceHistoryItem } from '@/shared/api/types';

export interface ChartPoint {
  time: number;
  value: number;
  source: PriceHistoryItem;
}

/** Value of a snapshot in hryvnia; null when it cannot be plotted. */
function uahValue(item: PriceHistoryItem): number | null {
  const raw = item.priceUah ?? (item.currencyCode === 'UAH' ? item.price : null);
  if (raw === null) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function toChartPoints(items: PriceHistoryItem[]): ChartPoint[] {
  return items
    .flatMap((item) => {
      const value = uahValue(item);
      const time = new Date(item.observedAt).getTime();
      return value === null || Number.isNaN(time) ? [] : [{ time, value, source: item }];
    })
    .sort((a, b) => a.time - b.time || a.source.id - b.source.id);
}
