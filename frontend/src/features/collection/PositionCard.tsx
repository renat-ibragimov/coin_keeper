import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CollectionPosition } from '@/shared/api/types';
import { formatDate, formatUah } from '@/shared/lib/format';
import { Badge, Button, CoinImage } from '@/shared/ui';

import styles from './PositionCard.module.css';

interface PositionCardProps {
  item: CollectionPosition;
}

/** One catalog item's card in "Мої монети": every purchase of it, rolled up. */
export function PositionCard({ item }: PositionCardProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const cardUrl = `/catalog/${item.catalogItemId}`;
  const addUrl = `/collection/coins/new?catalogItemId=${item.catalogItemId}`;
  const meta = [String(item.year), item.denomination].filter(Boolean).join(' · ');

  return (
    <article className={[styles.card, item.isArchived ? styles.archived : ''].join(' ')}>
      <Link to={cardUrl} className={styles.media} tabIndex={-1}>
        <CoinImage src={item.thumbnailUrl} alt="" className={styles.image} />
      </Link>
      <div className={styles.body}>
        <div className={styles.headline}>
          {/* title: the same native tooltip the catalogue tile carries — the
              heading clamps to two lines, so a long coin name is only
              readable in full on hover (CoinCard.tsx). */}
          <h3 className={styles.title} title={item.title}>
            <Link to={cardUrl} className={`${styles.titleLink} ${styles.titleLinkStretched}`}>
              {item.title}
            </Link>
          </h3>
          {item.grades.length > 0 ? <Badge>{item.grades.join(' · ')}</Badge> : null}
        </div>
        {item.seriesName ? <div className={styles.series}>{item.seriesName}</div> : null}
        <div className={styles.meta}>
          {item.country}
          {meta ? ` · ${meta}` : ''}
        </div>
        {item.isArchived ? (
          <div className={styles.archivedNote}>
            <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
          </div>
        ) : null}
        <dl className={styles.facts}>
          <div className={styles.fact}>
            <dt>{t('collection.quantity')}</dt>
            <dd className="tabular">{t('catalog.quantity', { count: item.totalQuantity })}</dd>
          </div>
          <div className={styles.fact}>
            <dt>{t('collection.spent')}</dt>
            <dd className="tabular">{formatUah(item.totalSpendUah, locale)}</dd>
          </div>
          <div className={styles.fact}>
            <dt>{t('collection.valuation')}</dt>
            <dd className="tabular">
              {item.marketValueUah !== null ? (
                formatUah(item.marketValueUah, locale)
              ) : (
                <span className={styles.muted}>{t('catalog.noPrice')}</span>
              )}
            </dd>
          </div>
          <div className={styles.fact}>
            <dt>{t('collection.lastAcquisition')}</dt>
            <dd className="tabular">
              {item.lastAcquisitionDate ? formatDate(item.lastAcquisitionDate, locale) : '—'}
            </dd>
          </div>
        </dl>
      </div>
      <div className={styles.footer}>
        <Link to={addUrl} className={styles.addLink}>
          <Button variant="secondary" size="sm" block>
            + {t('catalog.addAnotherCopy')}
          </Button>
        </Link>
      </div>
    </article>
  );
}
