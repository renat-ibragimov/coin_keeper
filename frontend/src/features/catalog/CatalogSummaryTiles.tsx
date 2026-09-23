import { CircleCheck, CircleDashed, PiggyBank, Wallet } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { CatalogSummary } from '@/shared/api/types';
import { formatNumber, formatUah } from '@/shared/lib/format';
import { StatTile } from '@/shared/ui';

import styles from './CatalogSummaryTiles.module.css';

interface CatalogSummaryTilesProps {
  data: CatalogSummary;
}

/**
 * The four coverage/money tiles on "Каталог", scoped to whatever filters the
 * browse screen currently carries — a different set from Огляд/Мої монети's
 * `CollectionSummaryTiles`, because this screen is about the catalog itself
 * (є/не вистачає/треба докупити), not the owner's collection as a whole
 * (owner's call, 2026-09-23). `owned` never narrows these: see
 * `fetchCatalogSummary`'s docstring. Not links, unlike the other tile rows:
 * there is no page besides this one to send the reader to, and a `/catalog`
 * link would have dropped whatever filters produced these very numbers
 * (same non-clickable pattern as `UsersSection.tsx`'s admin tiles).
 */
export function CatalogSummaryTiles({ data }: CatalogSummaryTilesProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  return (
    <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
      <StatTile
        icon={<CircleCheck strokeWidth={1.75} />}
        label={t('catalog.tileOwned')}
        value={formatNumber(data.owned, locale, 0)}
        hint={t('dashboard.progress', { owned: data.owned, count: data.total })}
      />
      <StatTile
        icon={<CircleDashed strokeWidth={1.75} />}
        label={t('catalog.tileMissing')}
        value={formatNumber(data.missing, locale, 0)}
        hint={
          data.unpricedMissing > 0
            ? t('dashboard.unpriced', { count: data.unpricedMissing })
            : undefined
        }
      />
      <StatTile
        icon={<Wallet strokeWidth={1.75} />}
        label={t('catalog.tileSpent')}
        value={formatUah(data.purchaseTotalUah, locale)}
      />
      <StatTile
        icon={<PiggyBank strokeWidth={1.75} />}
        label={t('catalog.tileMissingBudget')}
        value={formatUah(data.missingBudgetUah, locale)}
      />
    </section>
  );
}
