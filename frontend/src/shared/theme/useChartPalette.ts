import { useMemo } from 'react';

import { useTheme } from './useTheme';

export interface ChartPalette {
  /** Solid accent gold; the "primary" series (coin spending). */
  accent: string;
  /** A lighter accent tone for a secondary series (supporting expenses). */
  accentSoft: string;
  text: string;
  textMuted: string;
  grid: string;
  surface: string;
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
    const accent = readToken('--color-accent', '#96692a');
    const surface = readToken('--color-surface-raised', '#efe2c9');
    const shade = (share: number) =>
      `color-mix(in srgb, ${accent} ${Math.round(share * 100)}%, ${surface})`;
    return {
      accent,
      accentSoft: shade(0.45),
      text: readToken('--color-text', '#2a2117'),
      textMuted: readToken('--color-text-muted', '#83715d'),
      grid: readToken('--color-border', '#bfa77d'),
      surface,
      tooltipBg: readToken('--color-surface-raised', surface),
      tooltipBorder: readToken('--color-border-strong', '#a9895c'),
      shade,
      // theme is not read above, but re-running the memo on theme change is the point.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}
