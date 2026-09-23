import { Coins, Scale, TrendingUp, Wallet } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { formatNumber, formatSignedPercent, formatSignedUah, formatUah } from '@/shared/lib/format';
import { StatTile } from '@/shared/ui';

import { valueDelta } from './finance';
import styles from './CollectionSummaryTiles.module.css';

/** The five fields these tiles need — satisfied structurally by both the
 *  unfiltered `BootstrapOut['dashboard']` (Огляд) and the filtered
 *  `CollectionSummary` (Мої монети, scoped to the page's own filters). */
export interface CollectionSummaryTilesData {
  collectionItems: number;
  completedItems: number;
  totalSpendUah: string;
  relatedSpendUah: string;
  marketValueUah: string;
}

interface CollectionSummaryTilesProps {
  data: CollectionSummaryTilesData;
}

/**
 * The four money/coverage tiles shared by Огляд and Мої монети (each scoped
 * to its own filters, or lack of them) -- one row, one set of numbers,
 * everywhere it appears (owner's call, 2026-09-23).
 */
export function CollectionSummaryTiles({ data }: CollectionSummaryTilesProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const location = useLocation();
  const delta = valueDelta(data.totalSpendUah, data.marketValueUah);
  const deltaTone = delta.diffUah > 0 ? 'success' : delta.diffUah < 0 ? 'danger' : 'neutral';
  // On Мої монети itself this tile links to the page it's already on --
  // carry the current filters along so the click is a harmless no-op
  // instead of silently clearing them (a bare `/collection/coins` href
  // would drop the query string).
  const coinsHref =
    location.pathname === '/collection/coins'
      ? { pathname: '/collection/coins', search: location.search }
      : '/collection/coins';

  return (
    <section className={styles.tiles} aria-label={t('dashboard.tilesLabel')}>
      <Link to={coinsHref} className={styles.tileLink}>
        <StatTile
          icon={<Coins strokeWidth={1.75} />}
          label={t('dashboard.tileCoins')}
          value={formatNumber(data.collectionItems, locale, 0)}
          hint={t('dashboard.tileCoinsHint', { count: data.completedItems })}
        />
      </Link>
      <Link to="/collection/money" className={styles.tileLink}>
        <StatTile
          icon={<Wallet strokeWidth={1.75} />}
          label={t('dashboard.spentTotal')}
          value={formatUah(data.totalSpendUah, locale)}
          hint={t('dashboard.tileSpentHint', {
            amount: formatUah(data.relatedSpendUah, locale),
          })}
        />
      </Link>
      <Link to="/collection/money" className={styles.tileLink}>
        <StatTile
          icon={<TrendingUp strokeWidth={1.75} />}
          label={t('dashboard.marketValue')}
          value={formatUah(data.marketValueUah, locale)}
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
