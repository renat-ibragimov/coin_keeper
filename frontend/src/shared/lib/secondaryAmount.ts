import type { ExchangeRateOut } from '@/shared/api/types';
import { formatNumber } from '@/shared/lib/format';

export type SecondaryCurrency = 'USD' | 'EUR';

/** Picks the backend's own precomputed figure — a historical, purchase-date
 *  conversion (purchaseTotalUsd/Eur, totalUsd/Eur, amountUsd/Eur) — for
 *  whichever currency the viewer picked in settings.secondaryCurrency. */
export function pickSecondary<T>(usd: T, eur: T, currency: SecondaryCurrency): T {
  return currency === 'EUR' ? eur : usd;
}

/** The live secondary-currency/UAH rate from bootstrap's exchangeRates
 *  (docs/api.md), the same feed the dashboard's rate tiles use —
 *  null if NBU has none yet. Only ever the right choice for a CURRENT value:
 *  it has no purchase date of its own to look up a historical rate for. */
export function secondaryRateFrom(
  rates: ExchangeRateOut[] | undefined,
  currency: SecondaryCurrency,
): number | null {
  const rate = rates?.find((entry) => entry.code === currency);
  return rate?.rate ? Number(rate.rate) : null;
}

/** A live-rate UAH → secondary-currency conversion, for a value with no
 *  purchase date of its own (a current market valuation). null when there is
 *  no rate yet. */
export function toSecondary(uah: number, rate: number | null): number | null {
  if (rate === null || rate <= 0) return null;
  return uah / rate;
}

/** Formats an amount already in the secondary currency — the backend's own
 *  historical-rate conversion (pickSecondary(...)) or the live one from
 *  toSecondary(). null in, null out: the caller renders that as "no data",
 *  never a guess. */
export function formatSecondary(value: number | string | null, locale: string): string | null {
  return formatNumber(value, locale, 1);
}

export function formatSecondarySigned(value: number, locale: string): string {
  const formatted = formatSecondary(Math.abs(value), locale) ?? '0';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${formatted}`;
}
