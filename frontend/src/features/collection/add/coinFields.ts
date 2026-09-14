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
 * Material is the exception — its dictionary is seeded from what the
 * catalogue holds and says nothing about most issuers, so that one field
 * takes either.
 */
export interface CoinFields {
  issueYear: string;
  denominationId: string;
  seriesId: string;
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
  catalogKm: string;
  catalogUc: string;
  catalogNumista: string;
  notes: string;
}

export type CoinFieldErrors = Partial<Record<keyof CoinFields, string>>;

export function emptyCoinFields(): CoinFields {
  return {
    issueYear: '',
    denominationId: '',
    seriesId: '',
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
    catalogKm: '',
    catalogUc: '',
    catalogNumista: '',
    notes: '',
  };
}
