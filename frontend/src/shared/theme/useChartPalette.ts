import { useMemo } from 'react';

import { useTheme } from './useTheme';

export interface ChartPalette {
  /** Solid accent brass, for anything that has to match the interface accent. */
  accent: string;
  /** The primary series (coin spending): aged brass. */
  series1: string;
  /**
   * The secondary series (supporting expenses): a muted olive. Deliberately
   * a different hue family from series1 rather than a lighter tint of it —
   * two brass tones stacked in one bar were indistinguishable.
   */
  series2: string;
  text: string;
  textMuted: string;
  /** Axis ticks and labels: readable secondary contrast, not body contrast. */
  axis: string;
  grid: string;
  /** The raised card surface, used by shade() as the ramp's far end. */
  surface: string;
  /** The structural-panel surface the charts actually sit on: the colour a
   *  stacked bar or a donut segment separates against. */
  panel: string;
  tooltipBg: string;
  tooltipBorder: string;
  /** An accent tone mixed toward the surface, `share` in [0, 1] (1 = full accent). */
  shade(share: number): string;
}

function readToken(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** recharts needs literal color strings, not `var(...)`, so read the tokens once per theme. */
export function useChartPalette(): ChartPalette {
  const { theme } = useTheme();
  return useMemo(() => {
    const accent = readToken('--color-accent', '#8a6228');
    const surface = readToken('--color-surface-raised', '#eee8dd');
    const shade = (share: number) =>
      `color-mix(in srgb, ${accent} ${Math.round(share * 100)}%, ${surface})`;
    return {
      accent,
      series1: readToken('--color-chart-series-1', accent),
      series2: readToken('--color-chart-series-2', '#6c7050'),
      text: readToken('--color-text', '#211e1a'),
      textMuted: readToken('--color-text-muted', '#786f62'),
      axis: readToken('--color-chart-axis', '#786f62'),
      grid: readToken('--color-chart-grid', '#b4a892'),
      surface,
      panel: readToken('--color-surface', '#ddd5c8'),
      tooltipBg: readToken('--color-surface-raised', surface),
      tooltipBorder: readToken('--color-border-strong', '#756853'),
      shade,
      // theme is not read above, but re-running the memo on theme change is the point.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}
