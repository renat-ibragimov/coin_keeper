import { format, isValid, parse } from 'date-fns';

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
 * The query parameters the API understands for narrowing by period: an
 * exact year collapses to a one-year `yearFrom`/`yearTo`, "year range" sends
 * them as-is, and "date range" sends `dateFrom`/`dateTo` instead — narrowing
 * by `issue_date` with a fallback to `issue_year` when a coin only has the
 * year (docs/03-api-contract.md). One function, not one per mode: a caller
 * that read `dateFrom`/`dateTo` straight off `period` would leak a stale
 * date range into the request even while mode is "year" — switching modes
 * keeps the other modes' own values around instead of clearing them
 * (`PeriodFilter.tsx`), which is exactly what a mode-blind read would trip on.
 */
export function periodToApiParams(period: PeriodFilterValue): {
  yearFrom: number | undefined;
  yearTo: number | undefined;
  dateFrom: string | undefined;
  dateTo: string | undefined;
} {
  if (period.mode === 'year') {
    return { yearFrom: period.year, yearTo: period.year, dateFrom: undefined, dateTo: undefined };
  }
  if (period.mode === 'yearRange') {
    return {
      yearFrom: period.yearFrom,
      yearTo: period.yearTo,
      dateFrom: undefined,
      dateTo: undefined,
    };
  }
  return {
    yearFrom: undefined,
    yearTo: undefined,
    dateFrom: period.dateFrom,
    dateTo: period.dateTo,
  };
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

const DATE_INPUT_FORMATS: Record<string, string> = { uk: 'dd.MM.yyyy' };
const DEFAULT_DATE_FORMAT = 'MM/dd/yyyy';

/** The date-range fields' own display/typing format, per app language — the
 *  Ukrainian convention for `uk`, and the format the native `<input
 *  type="date">` this replaced already showed for `en` (owner's report,
 *  2026-09-22: the native picker's language followed the browser, not the
 *  app's uk/en toggle, no matter what `lang` was set on it — react-day-picker
 *  replaces it precisely so this can actually track the app's language). */
export function periodDateFormat(lang: string): string {
  return DATE_INPUT_FORMATS[lang] ?? DEFAULT_DATE_FORMAT;
}

/** Parses the `yyyy-MM-dd` shape `dateFrom`/`dateTo` are stored in (the
 *  native `<input type="date">` value shape, kept as the wire format even
 *  though the field itself no longer is one). `undefined` stays `undefined`. */
export function parsePeriodDate(value: string | undefined): Date | undefined {
  if (!value) return undefined;
  const parsed = parse(value, 'yyyy-MM-dd', new Date());
  return isValid(parsed) ? parsed : undefined;
}

export function formatPeriodDate(date: Date): string {
  return format(date, 'yyyy-MM-dd');
}

/** `dateFrom`/`dateTo` rendered in the app's current language — shared by the
 *  trigger's summary text and the removed-filter chip. */
export function formatPeriodDateForDisplay(
  value: string | undefined,
  lang: string,
): string | undefined {
  const date = parsePeriodDate(value);
  return date ? format(date, periodDateFormat(lang)) : undefined;
}
