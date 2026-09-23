import { Coins, Scale, TrendingUp, Wallet } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { BootstrapOut } from '@/shared/api/types';
import { formatNumber, formatSignedPercent, formatSignedUah, formatUah } from '@/shared/lib/format';
import { StatTile } from '@/shared/ui';

import { valueDelta } from './finance';
import styles from './CollectionSummaryTiles.module.css';

interface CollectionSummaryTilesProps {
  dashboard: BootstrapOut['dashboard'];
}

/**
 * The four money/coverage tiles shared by Огляд, Мої монети and (for a
 * signed-in owner with something in their collection) Каталог -- one row,
 * one set of numbers, everywhere it appears (owner's call, 2026-09-23).
 */
export function CollectionSummaryTiles({ dashboard }: CollectionSummaryTilesProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const delta = valueDelta(dashboard.totalSpendUah, dashboard.marketValueUah);
  const deltaTone = delta.diffUah > 0 ? 'success' : delta.diffUah < 0 ? 'danger' : 'neutral';

  return (
    <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
      <Link to="/collection/coins" className={styles.tileLink}>
        <StatTile
          icon={<Coins strokeWidth={1.75} />}
          label={t('dashboard.tileCoins')}
          value={formatNumber(dashboard.collectionItems, locale, 0)}
          hint={t('dashboard.tileCoinsHint', { count: dashboard.completedItems })}
        />
      </Link>
      <Link to="/collection/money" className={styles.tileLink}>
        <StatTile
          icon={<Wallet strokeWidth={1.75} />}
          label={t('dashboard.spentTotal')}
          value={formatUah(dashboard.totalSpendUah, locale)}
          hint={t('dashboard.tileSpentHint', {
            amount: formatUah(dashboard.relatedSpendUah, locale),
          })}
        />
      </Link>
      <Link to="/collection/money" className={styles.tileLink}>
        <StatTile
          icon={<TrendingUp strokeWidth={1.75} />}
          label={t('dashboard.marketValue')}
          value={formatUah(dashboard.marketValueUah, locale)}
        />
      </Link>
      <Link to="/collection/money" className={styles.tileLink}>
        <StatTile
          icon={<Scale strokeWidth={1.75} />}
          label={t('dashboard.delta')}
          value={formatSignedUah(delta.diffUah, locale)}
          hint={delta.percent !== null ? formatSignedPercent(delta.percent, locale) : undefined}
          tone={deltaTone}
        />
      </Link>
    </section>
  );
}
