import type { TFunction } from 'i18next';

import type { CatalogCard } from '@/shared/api/types';
import { formatDate, formatNumber } from '@/shared/lib/format';
import type { PropertyRow } from '@/shared/ui';

const METAL_LABELS = {
  precious: 'catalog.metalPrecious',
  base: 'catalog.metalBase',
  unknown: 'catalog.metalUnknown',
} as const;

/** Catalog numbers in one line: "KM# 123 · UC# 45 · Numista 678". */
export function catalogNumbers(card: CatalogCard): string | null {
  const parts = [
    card.catalogKm ? `KM# ${card.catalogKm}` : null,
    card.catalogUc ? `UC# ${card.catalogUc}` : null,
    card.catalogNumista ? `Numista ${card.catalogNumista}` : null,
  ].filter(Boolean);
  // The generic number is shown only when it is not one of the named ones.
  if (card.catalogNumber && !parts.some((part) => part?.includes(card.catalogNumber!))) {
    parts.unshift(card.catalogNumber);
  }
  return parts.length ? parts.join(' · ') : null;
}

/** The "Характеристики" rows; PropertyList drops the empty ones. */
export function specRows(card: CatalogCard, t: TFunction, locale: string): PropertyRow[] {
  const mintage = card.mintageActual ?? card.mintageAnnounced;
  const unit = (value: string | null, suffix: string) => {
    const formatted = formatNumber(value, locale, 3);
    return formatted === null ? null : `${formatted} ${suffix}`;
  };
  return [
    { key: 'country', label: t('card.specCountry'), value: card.country },
    { key: 'series', label: t('card.specSeries'), value: card.seriesName },
    { key: 'year', label: t('card.specYear'), value: <span className="tabular">{card.year}</span> },
    {
      key: 'issueDate',
      label: t('card.specIssueDate'),
      value: formatDate(card.issueDate, locale),
    },
    {
      key: 'denomination',
      label: t('card.specDenomination'),
      value: card.denomination?.label ?? null,
    },
    {
      key: 'metal',
      label: t('card.specMetal'),
      value:
        card.metalKind === 'unknown' && !card.composition && !card.material
          ? null
          : t(METAL_LABELS[card.metalKind]),
    },
    {
      key: 'material',
      label: t('card.specMaterial'),
      // The dictionary name when the composition was recognised; otherwise
      // whatever text the source gave us.
      value: card.composition?.name ?? card.material,
    },
    { key: 'variety', label: t('card.specVariety'), value: card.variety },
    { key: 'subtype', label: t('card.specSubtype'), value: card.subtype },
    { key: 'catalogNumbers', label: t('card.specCatalogNumbers'), value: catalogNumbers(card) },
    {
      key: 'mintage',
      label:
        mintage === card.mintageActual ? t('card.specMintage') : t('card.specMintageAnnounced'),
      value: mintage === null ? null : formatNumber(mintage, locale, 0),
    },
    { key: 'diameter', label: t('card.specDiameter'), value: unit(card.diameterMm, t('units.mm')) },
    { key: 'weight', label: t('card.specWeight'), value: unit(card.weightGrams, t('units.g')) },
    {
      key: 'thickness',
      label: t('card.specThickness'),
      value: unit(card.thicknessMm, t('units.mm')),
    },
    { key: 'shape', label: t('card.specShape'), value: card.shape },
    { key: 'edge', label: t('card.specEdge'), value: card.edge },
    { key: 'orientation', label: t('card.specOrientation'), value: card.orientation },
  ];
}
