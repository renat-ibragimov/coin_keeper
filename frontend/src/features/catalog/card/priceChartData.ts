import type { ChartPoint } from './chartData';

export interface SeriesPoint {
  /** Unix seconds; strictly ascending and unique within one `series` array. */
  time: number;
  value: number;
  sourceId: number;
}

export type MarkerKind = 'own' | 'suspect';

export interface MarkerPoint {
  sourceId: number;
  time: number;
  value: number;
  kind: MarkerKind;
}

export interface PriceSeriesData {
  series: SeriesPoint[];
  markers: MarkerPoint[];
}

/**
 * Splits price history into what the chart actually draws: a continuous
 * trend line with suspect snapshots excluded (so one bad price never
 * stretches the whole scale — the old chart's "worm"), plus markers for the
 * two point kinds worth calling out. lightweight-charts requires strictly
 * ascending, unique series times; two snapshots recorded the same second are
 * nudged a second apart rather than dropped.
 */
export function buildPriceSeries(points: ChartPoint[]): PriceSeriesData {
  const series: SeriesPoint[] = [];
  const markers: MarkerPoint[] = [];
  let lastTime = Number.NEGATIVE_INFINITY;

  for (const point of points) {
    const seconds = Math.floor(point.time / 1000);
    if (point.source.isSuspect) {
      markers.push({
        sourceId: point.source.id,
        time: seconds,
        value: point.value,
        kind: 'suspect',
      });
      continue;
    }
    const time = seconds <= lastTime ? lastTime + 1 : seconds;
    lastTime = time;
    series.push({ time, value: point.value, sourceId: point.source.id });
    if (point.source.isOwn) {
      markers.push({ sourceId: point.source.id, time, value: point.value, kind: 'own' });
    }
  }

  markers.sort((a, b) => a.time - b.time);
  return { series, markers };
}

export type RangePreset = '1m' | '6m' | '1y' | 'all';

/** Start of a quick-range preset, anchored to the series' most recent point. */
export function rangeStart(latestSeconds: number, preset: RangePreset): number {
  if (preset === 'all') return Number.NEGATIVE_INFINITY;
  const date = new Date(latestSeconds * 1000);
  if (preset === '1m') date.setUTCMonth(date.getUTCMonth() - 1);
  else if (preset === '6m') date.setUTCMonth(date.getUTCMonth() - 6);
  else date.setUTCFullYear(date.getUTCFullYear() - 1);
  return Math.floor(date.getTime() / 1000);
}
