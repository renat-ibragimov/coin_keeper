import type { CollectionItem } from '@/shared/api/types';
import { formatUah } from '@/shared/lib/format';

/** Query keys whose data changes when an instance appears, changes or disappears. */
export const COLLECTION_DEPENDENT_KEYS = [
  'collection',
  'bootstrap',
  'catalog',
  'expenses',
  'series',
];

/** Current valuation of the instance: latest visible price × quantity. */
export function instanceValuation(item: CollectionItem, locale: string): string | null {
  if (item.marketPriceUah === null) return null;
  return formatUah(Number(item.marketPriceUah) * item.quantity, locale);
}
