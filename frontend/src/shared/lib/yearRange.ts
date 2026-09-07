import type { CountryOut } from '@/shared/api/types';

export interface YearBounds {
  min: number;
  max: number;
}

const FALLBACK_MIN_YEAR = 1900;

function fallbackBounds(): YearBounds {
  return { min: FALLBACK_MIN_YEAR, max: new Date().getFullYear() };
}

/**
 * Overall bounds for a year filter: the selected country's own minYear/maxYear
 * when it has any coins at all, otherwise the span across every country in
 * the loaded list (countries with no coins skipped), otherwise 1900..this
 * year — an empty or bound-less directory still has to render two workable
 * dropdowns (docs/03-api-contract.md, docs/08-ui-map.md).
 */
export function computeYearBounds(
  countries: CountryOut[],
  countryId: number | undefined,
): YearBounds {
  const country = countryId !== undefined ? countries.find((c) => c.id === countryId) : undefined;
  if (country && country.minYear != null && country.maxYear != null) {
    return { min: country.minYear, max: country.maxYear };
  }
  const years = countries.flatMap((c) =>
    c.minYear != null && c.maxYear != null ? [c.minYear, c.maxYear] : [],
  );
  if (years.length === 0) return fallbackBounds();
  return { min: Math.min(...years), max: Math.max(...years) };
}

/** Every year in `bounds`, oldest first — the order a "from" or "to" list
 *  reads most naturally in (owner's call, 2026-09-07). */
export function buildYearList(bounds: YearBounds): number[] {
  const years: number[] = [];
  for (let year = bounds.min; year <= bounds.max; year++) years.push(year);
  return years;
}

/** Pulls a possibly out-of-range value back inside `bounds`; `undefined` stays `undefined`. */
export function clampYear(value: number | undefined, bounds: YearBounds): number | undefined {
  if (value === undefined) return undefined;
  if (value < bounds.min) return bounds.min;
  if (value > bounds.max) return bounds.max;
  return value;
}
