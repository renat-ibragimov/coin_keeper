import type { ExchangeRateOut } from '@/shared/api/types';
import { formatNumber } from '@/shared/lib/format';

/** The live USD/UAH rate from bootstrap's exchangeRates (docs/03-api-contract.md),
 *  the same feed the dashboard's rate tiles use — null if NBU has none yet.
 *  Only ever the right choice for a CURRENT value: it has no purchase date
 *  of its own to look up a historical rate for. */
export function usdRateFrom(rates: ExchangeRateOut[] | undefined): number | null {
  const usd = rates?.find((rate) => rate.code === 'USD');
  return usd?.rate ? Number(usd.rate) : null;
}

/** A live-rate UAH → USD conversion, for a value with no purchase date of
 *  its own (a current market valuation). null when there is no rate yet. */
export function toUsd(uah: number, usdRate: number | null): number | null {
  if (usdRate === null || usdRate <= 0) return null;
  return uah / usdRate;
}

/** Formats an amount already in USD — the backend's own historical-rate
 *  conversion (purchaseTotalUsd, totalUsd) or the live one from toUsd().
 *  null in, null out: the caller renders that as "no data", never a guess. */
export function formatUsd(usd: number | string | null, locale: string): string | null {
  return formatNumber(usd, locale, 1);
}

export function formatUsdSigned(usd: number, locale: string): string {
  const formatted = formatUsd(Math.abs(usd), locale) ?? '0';
  const sign = usd > 0 ? '+' : usd < 0 ? '−' : '';
  return `${sign}${formatted}`;
}
