import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CatalogListItem } from '@/shared/api/types';
import { coinTitle } from '@/shared/lib/coinTitle';
import { formatUah } from '@/shared/lib/format';
import { priceSourceLabel } from '@/shared/lib/priceSource';
import { Badge, CoinImage } from '@/shared/ui';

import styles from './CoinCard.module.css';

function CoinImages({ item }: { item: CatalogListItem }) {
  const sides = [item.obverseImageUrl, item.reverseImageUrl].filter(Boolean);
  // With one side stored, or none at all, a single frame spans the media area;
  // CoinImage decides on its own whether it shows a photo or the placeholder.
  if (sides.length < 2) {
    return <CoinImage src={sides[0]} alt="" className={styles.imageSingle} />;
  }
  return (
    <>
      <CoinImage src={item.obverseImageUrl} alt="" className={styles.image} />
      <CoinImage src={item.reverseImageUrl} alt="" className={styles.image} />
    </>
  );
}

interface CoinCardProps {
  item: CatalogListItem;
  /** Optional call to action under the price, e.g. "Add a purchase". */
  action?: ReactNode;
}

export function CoinCard({ item, action }: CoinCardProps) {
  const { t, i18n } = useTranslation();
  const price = formatUah(item.marketPriceUah, i18n.language);
  const owned = item.quantityOwned > 0;
  const title = coinTitle(item);
  const cardUrl = `/catalog/${item.id}`;

  return (
    <article className={[styles.card, item.isArchived ? styles.archived : ''].join(' ')}>
      <div className={styles.media}>
        <Link to={cardUrl} className={styles.mediaLink} aria-label={title} tabIndex={-1}>
          <CoinImages item={item} />
        </Link>
        <span className={styles.mediaBadges}>
          {item.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
          {item.isArchived ? <Badge tone="warning">{t('catalog.badgeArchived')}</Badge> : null}
        </span>
      </div>
      <div className={styles.body}>
        {item.denomination ? <div className={styles.denomination}>{item.denomination}</div> : null}
        <h3 className={styles.title}>
          <Link to={cardUrl} className={styles.titleLink}>
            {title}
          </Link>
        </h3>
        <div className={styles.meta}>
          {item.country} · <span className="tabular">{item.year}</span>
        </div>
        {item.seriesName ? <div className={styles.series}>{item.seriesName}</div> : null}
        <div className={styles.availability}>
          {owned ? (
            <Badge tone="success">
              ✓ {t('catalog.badgeInCollection')}
              {item.quantityOwned > 1 ? ` · ${item.quantityOwned}` : ''}
            </Badge>
          ) : (
            <Badge tone="danger">✕ {t('catalog.badgeMissing')}</Badge>
          )}
        </div>
        {/* sourceUrl points at the uCoin page, not at a file: a link, never an image. */}
        {item.sourceUrl ? (
          <a className={styles.source} href={item.sourceUrl} target="_blank" rel="noreferrer">
            {t('catalog.sourceLink')} ↗
          </a>
        ) : null}
      </div>
      <div className={styles.footer}>
        {price ? (
          <span
            className={`${styles.price} tabular`}
            title={priceSourceLabel(item.priceSource, t) || undefined}
          >
            {price}
          </span>
        ) : (
          <span className={styles.noPrice}>{t('catalog.noPrice')}</span>
        )}
        {item.priceSource ? (
          <span className={styles.priceSource}>
            {t('catalog.priceSource', { source: priceSourceLabel(item.priceSource, t) })}
          </span>
        ) : null}
      </div>
      {action ? <div className={styles.action}>{action}</div> : null}
    </article>
  );
}
