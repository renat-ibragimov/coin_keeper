import type { TFunction } from 'i18next';

/** Human name of a price snapshot source; unknown codes are shown as they are. */
export function priceSourceLabel(source: string | null | undefined, t: TFunction): string {
  if (!source) return '';
  const key = `sources.${source.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return t(key, { defaultValue: source });
}
