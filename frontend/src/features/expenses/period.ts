export type ExpensesPeriodPreset = '1m' | '3m' | '6m' | '1y';

const PRESET_MONTHS: Record<ExpensesPeriodPreset, number> = { '1m': 1, '3m': 3, '6m': 6, '1y': 12 };

function daysInMonth(year: number, monthIndex0: number): number {
  return new Date(year, monthIndex0 + 1, 0).getDate();
}

function isoDate(year: number, month1: number, day: number): string {
  return `${year}-${String(month1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * `date` shifted by whole calendar months (negative goes back), clamped to
 * the last day of the target month — the same rule the backend's
 * `_shift_month` uses, so "1 year back from 31 Aug" lands on the same day a
 * preset button and its server-side range agree on.
 */
function shiftMonths(date: Date, months: number): string {
  const total = date.getFullYear() * 12 + date.getMonth() + months;
  const year = Math.floor(total / 12);
  const month0 = ((total % 12) + 12) % 12;
  const day = Math.min(date.getDate(), daysInMonth(year, month0));
  return isoDate(year, month0 + 1, day);
}

/** Today's calendar date and the range's start, both as "YYYY-MM-DD". */
export function presetRange(
  preset: ExpensesPeriodPreset,
  today: Date = new Date(),
): { dateFrom: string; dateTo: string } {
  return {
    dateFrom: shiftMonths(today, -PRESET_MONTHS[preset]),
    dateTo: shiftMonths(today, 0),
  };
}
