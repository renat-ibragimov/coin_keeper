export type PeriodMode = 'year' | 'yearRange' | 'dateRange';

export interface PeriodFilterValue {
  mode: PeriodMode;
  year?: number;
  yearFrom?: number;
  yearTo?: number;
  /** yyyy-mm-dd, the native <input type="date"> value shape. */
  dateFrom?: string;
  dateTo?: string;
}

const DEFAULT_PERIOD: PeriodFilterValue = { mode: 'yearRange' };

function intOrUndefined(raw: string | null): number | undefined {
  if (!raw) return undefined;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/**
 * Parses the period.* query params shared by the catalog and collection
 * filters (docs/03-api-contract.md). A missing `periodMode` falls back to
 * "yearRange" when `yearFrom`/`yearTo` are present — the shape every link
 * shared before this filter existed already has — and to the empty default
 * otherwise, so old links keep resolving to the same listing.
 */
export function parsePeriod(params: URLSearchParams): PeriodFilterValue {
  const mode = params.get('periodMode');
  const year = intOrUndefined(params.get('year'));
  const yearFrom = intOrUndefined(params.get('yearFrom'));
  const yearTo = intOrUndefined(params.get('yearTo'));
  const dateFrom = params.get('dateFrom') || undefined;
  const dateTo = params.get('dateTo') || undefined;

  if (mode === 'year' || mode === 'yearRange' || mode === 'dateRange') {
    return { mode, year, yearFrom, yearTo, dateFrom, dateTo };
  }
  if (yearFrom !== undefined || yearTo !== undefined) {
    return { mode: 'yearRange', yearFrom, yearTo };
  }
  return DEFAULT_PERIOD;
}

/** Writes only the active mode's own fields, plus `periodMode` when it isn't
 *  the "yearRange" default — keeps a plain year-range URL exactly as before. */
export function serializePeriod(params: URLSearchParams, period: PeriodFilterValue): void {
  if (period.mode === 'year') {
    if (period.year !== undefined) params.set('year', String(period.year));
    params.set('periodMode', 'year');
  } else if (period.mode === 'dateRange') {
    if (period.dateFrom) params.set('dateFrom', period.dateFrom);
    if (period.dateTo) params.set('dateTo', period.dateTo);
    params.set('periodMode', 'dateRange');
  } else {
    if (period.yearFrom !== undefined) params.set('yearFrom', String(period.yearFrom));
    if (period.yearTo !== undefined) params.set('yearTo', String(period.yearTo));
  }
}

/**
 * The `issue_year` range the API currently understands: an exact year
 * collapses to a one-year range, and the date-range mode has no backend
 * support yet, so it narrows nothing until that lands.
 */
export function periodToYearRange(period: PeriodFilterValue): {
  yearFrom: number | undefined;
  yearTo: number | undefined;
} {
  if (period.mode === 'year') return { yearFrom: period.year, yearTo: period.year };
  if (period.mode === 'yearRange') return { yearFrom: period.yearFrom, yearTo: period.yearTo };
  return { yearFrom: undefined, yearTo: undefined };
}

export function hasPeriodValue(period: PeriodFilterValue): boolean {
  return (
    period.year !== undefined ||
    period.yearFrom !== undefined ||
    period.yearTo !== undefined ||
    Boolean(period.dateFrom) ||
    Boolean(period.dateTo)
  );
}
