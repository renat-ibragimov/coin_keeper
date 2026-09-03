/** Locale-aware formatting of the values the API sends as strings.
 *
 * Money arrives as strings ("666.00") to keep precision; these helpers turn
 * them into display text and never feed a result back into arithmetic.
 */

function intlLocale(locale: string): string {
  return locale === 'uk' ? 'uk-UA' : 'en-GB';
}

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}

export function formatNumber(
  value: string | number | null | undefined,
  locale: string,
  fractionDigits = 2,
): string | null {
  const amount = toNumber(value);
  if (amount === null) return null;
  return new Intl.NumberFormat(intlLocale(locale), {
    minimumFractionDigits: 0,
    maximumFractionDigits: fractionDigits,
  }).format(amount);
}

export function formatUah(
  value: string | number | null | undefined,
  locale: string,
): string | null {
  const formatted = formatNumber(value, locale);
  return formatted === null ? null : `${formatted} ₴`;
}

/** "+1 234 ₴" / "−1 234 ₴" / "0 ₴" — the sign is always spelled out. */
export function formatSignedUah(value: string | number | null | undefined, locale: string) {
  const amount = toNumber(value);
  if (amount === null) return null;
  const magnitude = formatNumber(Math.abs(amount), locale) ?? '0';
  const sign = amount > 0 ? '+' : amount < 0 ? '−' : '';
  return `${sign}${magnitude} ₴`;
}

/** "+12,5 %" / "−3 %" with at most one decimal. */
export function formatSignedPercent(value: number | null | undefined, locale: string) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const magnitude = formatNumber(Math.abs(value), locale, 1) ?? '0';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${magnitude} %`;
}

export function formatPercent(value: number | null | undefined, locale: string, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${formatNumber(value, locale, digits) ?? '0'} %`;
}

const CURRENCY_SYMBOLS: Record<string, string> = { UAH: '₴', USD: '$', EUR: '€' };

export function currencySymbol(code: string | null | undefined): string {
  if (!code) return '';
  return CURRENCY_SYMBOLS[code.toUpperCase()] ?? code.toUpperCase();
}

/** "350 ₴", "12,5 $", "10 €"; unknown codes stay as the ISO code. */
export function formatMoney(
  value: string | number | null | undefined,
  currency: string | null | undefined,
  locale: string,
): string | null {
  const formatted = formatNumber(value, locale);
  if (formatted === null) return null;
  const symbol = currencySymbol(currency ?? 'UAH');
  return `${formatted} ${symbol}`;
}

/** A calendar date or ISO timestamp → "02.04.2025" (uk) / "02/04/2025" (en). */
export function formatDate(value: string | null | undefined, locale: string): string | null {
  if (!value) return null;
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(intlLocale(locale), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

/** Short axis label: "тра. 2024" / "May 2024". */
export function formatMonthYear(value: string | Date, locale: string): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(intlLocale(locale), { month: 'short', year: 'numeric' }).format(
    date,
  );
}
