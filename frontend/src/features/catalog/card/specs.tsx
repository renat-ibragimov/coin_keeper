import type { TFunction } from 'i18next';

import type { CatalogCard, CollectionGroup } from '@/shared/api/types';
import { formatDate, formatNumber } from '@/shared/lib/format';
import type { PropertyRow } from '@/shared/ui';

const METAL_LABELS = {
  precious: 'catalog.metalPrecious',
  base: 'catalog.metalBase',
  unknown: 'catalog.metalUnknown',
} as const;

/* catalog.type* is phrased as a filter option ("Пам'ятні"), an adjective
 * agreeing with a plural "монети" — wrong grammar for a single coin's own
 * chip, which needs the singular noun phrase instead. */
const COLLECTION_GROUP_LABELS: Record<CollectionGroup, string> = {
  circulation: 'card.collectionGroupCirculation',
  commemorative: 'card.collectionGroupCommemorative',
  collector: 'card.collectionGroupCollector',
  other: 'card.collectionGroupOther',
};

/** The category chip next to the title: "Пам'ятна монета", "Обігова" и т.д. */
export function collectionGroupLabel(group: CollectionGroup, t: TFunction): string {
  return t(COLLECTION_GROUP_LABELS[group]);
}

/** "Нейзильбер" — the composition dictionary name, the free-text material, or the metal kind. */
function metalMaterial(card: CatalogCard, t: TFunction): string | null {
  if (card.composition?.name) return card.composition.name;
  if (card.material) return card.material;
  return card.metalKind === 'unknown' ? null : t(METAL_LABELS[card.metalKind]);
}

/** "Основна інформація": the coin's identity — country, series, category, year, denomination. */
export function identitySpecRows(card: CatalogCard, t: TFunction): PropertyRow[] {
  return [
    { key: 'country', label: t('card.specCountry'), value: card.country },
    { key: 'series', label: t('card.specSeries'), value: card.seriesName },
    {
      key: 'category',
      label: t('card.specCategory'),
      value: collectionGroupLabel(card.collectionGroup, t),
    },
    { key: 'year', label: t('card.specYear'), value: <span className="tabular">{card.year}</span> },
    {
      key: 'denomination',
      label: t('card.specDenomination'),
      value: card.denomination?.label ?? null,
    },
  ];
}

/** "Випуск": the release facts. */
export function issueSpecRows(card: CatalogCard, t: TFunction, locale: string): PropertyRow[] {
  return [
    {
      key: 'issueDate',
      label: t('card.specIssueDate'),
      value: formatDate(card.issueDate, locale),
    },
    {
      key: 'mintageAnnounced',
      label: t('card.specMintageAnnounced'),
      value: formatNumber(card.mintageAnnounced, locale, 0),
    },
    {
      key: 'mintageActual',
      label: t('card.specMintageActual'),
      value: formatNumber(card.mintageActual, locale, 0),
    },
    { key: 'variety', label: t('card.specVariety'), value: card.variety },
    { key: 'subtype', label: t('card.specSubtype'), value: card.subtype },
  ];
}

/** "Технічні характеристики": the coin's physical properties. */
export function technicalSpecRows(card: CatalogCard, t: TFunction, locale: string): PropertyRow[] {
  const unit = (value: string | null, suffix: string) => {
    const formatted = formatNumber(value, locale, 3);
    return formatted === null ? null : `${formatted} ${suffix}`;
  };
  return [
    { key: 'metalMaterial', label: t('card.specMetalMaterial'), value: metalMaterial(card, t) },
    { key: 'weight', label: t('card.specWeight'), value: unit(card.weightGrams, t('units.g')) },
    { key: 'diameter', label: t('card.specDiameter'), value: unit(card.diameterMm, t('units.mm')) },
    {
      key: 'thickness',
      label: t('card.specThickness'),
      value: unit(card.thicknessMm, t('units.mm')),
    },
    { key: 'edge', label: t('card.specEdge'), value: card.edge },
    { key: 'shape', label: t('card.specShape'), value: card.shape },
    { key: 'orientation', label: t('card.specOrientation'), value: card.orientation },
  ];
}

/**
 * Who to credit for the photos — moved here (out of an overlay on the photo
 * itself) so the attribution text never sits on top of the coin. One row
 * when both sides share a source, two when they don't.
 */
function imageSourceRows(card: CatalogCard, t: TFunction): PropertyRow[] {
  const obverse = card.obverseImage?.attribution ?? null;
  const reverse = card.reverseImage?.attribution ?? null;
  if (obverse && obverse === reverse) {
    return [{ key: 'imageSource', label: t('card.specImageSource'), value: obverse }];
  }
  return [
    { key: 'obverseImageSource', label: t('card.specObverseImageSource'), value: obverse },
    { key: 'reverseImageSource', label: t('card.specReverseImageSource'), value: reverse },
  ];
}

/** "Каталожна інформація": catalog reference numbers and photo attribution. */
export function catalogSpecRows(card: CatalogCard, t: TFunction): PropertyRow[] {
  const namedNumbers = [card.catalogKm, card.catalogUc, card.catalogNumista];
  const genericNumber =
    card.catalogNumber && !namedNumbers.includes(card.catalogNumber) ? card.catalogNumber : null;
  return [
    { key: 'catalogKm', label: t('card.specCatalogKm'), value: card.catalogKm },
    { key: 'catalogUc', label: t('card.specCatalogUc'), value: card.catalogUc },
    { key: 'catalogNumista', label: t('card.specCatalogNumista'), value: card.catalogNumista },
    { key: 'catalogNumber', label: t('card.specCatalogNumber'), value: genericNumber },
    ...imageSourceRows(card, t),
  ];
}
