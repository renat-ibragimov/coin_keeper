import type { CollectionGroup, MetalKind } from '@/shared/api/types';

export const COLLECTION_GROUPS: CollectionGroup[] = [
  'commemorative',
  'circulation',
  'collector',
  'other',
];

export const METAL_KINDS: MetalKind[] = ['unknown', 'precious', 'base'];

/**
 * Everything "Про монету" collects, as the strings the inputs hold.
 *
 * Edge and quality are dictionary ids, not free text: both have had a
 * dictionary of their own since 2026-09-12 (docs/04-business-rules.md, §14),
 * and a typed-in edge would never match what the catalogue parser stores.
 *
 * Material, denomination and series are the other way round — each is one
 * combobox over "the dictionary, or your own words", because all three
 * dictionaries are seeded from what the catalogue actually holds and say
 * nothing at all about most issuers (owner, 2026-09-14). The page resolves a
 * typed value against the list on submit: a match sends the id, anything
 * else sends the text.
 */
export interface CoinFields {
  issueYear: string;
  /** Text, not an id: matched against the country's dictionary on submit. */
  denomination: string;
  series: string;
  collectionGroup: CollectionGroup;
  material: string;
  metalKind: MetalKind;
  mintageAnnounced: string;
  weightGrams: string;
  diameterMm: string;
  thicknessMm: string;
  edgeTypeId: string;
  qualityTypeId: string;
  shape: string;
  /** One number: the collector has it and no reason to know whose catalogue
   *  it belongs to (owner, 2026-09-14). */
  catalogNumber: string;
  /** The coin in the collector's own words — three parts, as the catalogue's
   *  own `descriptions` column is shaped (docs/02-data-model.md). */
  description: string;
  descriptionObverse: string;
  descriptionReverse: string;
}

export type CoinFieldErrors = Partial<Record<keyof CoinFields, string>>;

export function emptyCoinFields(): CoinFields {
  return {
    issueYear: '',
    denomination: '',
    series: '',
    collectionGroup: 'commemorative',
    material: '',
    metalKind: 'unknown',
    mintageAnnounced: '',
    weightGrams: '',
    diameterMm: '',
    thicknessMm: '',
    edgeTypeId: '',
    qualityTypeId: '',
    shape: '',
    catalogNumber: '',
    description: '',
    descriptionObverse: '',
    descriptionReverse: '',
  };
}
