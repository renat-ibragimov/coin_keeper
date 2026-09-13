import type { ExchangeRateOut } from '@/shared/api/types';
import { formatNumber } from '@/shared/lib/format';

/** The live USD/UAH rate from bootstrap's exchangeRates (docs/03-api-contract.md),
 *  the same feed the dashboard's rate tiles use — null if NBU has none yet. */
export function usdRateFrom(rates: ExchangeRateOut[] | undefined): number | null {
  const usd = rates?.find((rate) => rate.code === 'USD');
  return usd?.rate ? Number(usd.rate) : null;
}

/** A "≈$" hint for a UAH amount, by the current rate — not the historical
 *  rate of any one purchase, so this is a ballpark for the aggregate strip,
 *  not a stand-in for purchaseRateUah on an individual instance. null when
 *  no rate is available yet, for the caller to render as "no data". */
export function approxUsd(uah: number, usdRate: number | null, locale: string): string | null {
  if (usdRate === null || usdRate <= 0) return null;
  return formatNumber(Math.abs(uah) / usdRate, locale, 1);
}

export function approxUsdSigned(
  uah: number,
  usdRate: number | null,
  locale: string,
): string | null {
  const value = approxUsd(uah, usdRate, locale);
  if (value === null) return null;
  const sign = uah > 0 ? '+' : uah < 0 ? '−' : '';
  return `${sign}${value}`;
}
