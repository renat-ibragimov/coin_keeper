import { formatNumber } from '@/shared/lib/format';

// TODO(nbu-rates): a flat mock rate for the coin card's UAH→USD hints — there
// is no historical NBU rate feed on this page yet (docs/11-roadmap.md). The
// same rate everywhere is intentional: it is here to preview the layout, not
// to give a real figure.
export const MOCK_UAH_PER_USD = 41.5;

export function mockUsd(uah: number, locale: string): string {
  return formatNumber(Math.abs(uah) / MOCK_UAH_PER_USD, locale, 1) ?? '0';
}

export function mockUsdSigned(uah: number, locale: string): string {
  const sign = uah > 0 ? '+' : uah < 0 ? '−' : '';
  return `${sign}${mockUsd(uah, locale)}`;
}
