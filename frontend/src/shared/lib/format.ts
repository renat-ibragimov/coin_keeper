/** Money arrives from the API as strings ("666.00") to keep precision. */
export function formatUah(value: string | null | undefined, locale: string): string | null {
  if (value === null || value === undefined || value === '') return null;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  const formatted = new Intl.NumberFormat(locale === 'uk' ? 'uk-UA' : 'en-GB', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
  return `${formatted} ₴`;
}
