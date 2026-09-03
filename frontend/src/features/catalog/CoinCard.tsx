import { useTranslation } from 'react-i18next';

import type { CatalogListItem } from '@/shared/api/types';
import { formatUah } from '@/shared/lib/format';
import { Badge } from '@/shared/ui';

import styles from './CoinCard.module.css';

function CoinImages({ item }: { item: CatalogListItem }) {
  const images = [item.obverseImageUrl, item.reverseImageUrl].filter((url): url is string => !!url);
  if (images.length === 0) {
    return (
      <div className={styles.placeholder} aria-hidden="true">
        ◎
      </div>
    );
  }
  return (
    <>
      {images.map((url, index) => (
        <img
          key={index}
          src={url}
          alt=""
          loading="lazy"
          className={images.length === 1 ? styles.imageSingle : styles.image}
        />
      ))}
    </>
  );
}

export function CoinCard({ item }: { item: CatalogListItem }) {
  const { t, i18n } = useTranslation();
  const price = formatUah(item.marketPriceUah, i18n.language);
  const owned = item.quantityOwned > 0;

  return (
    <article className={[styles.card, item.isArchived ? styles.archived : ''].join(' ')}>
      <div className={styles.media}>
        <CoinImages item={item} />
        <span className={styles.mediaBadges}>
          {item.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
          {item.isArchived ? <Badge tone="warning">{t('catalog.badgeArchived')}</Badge> : null}
        </span>
      </div>
      <div className={styles.body}>
        {item.denomination ? <div className={styles.denomination}>{item.denomination}</div> : null}
        <h3 className={styles.title}>{item.title}</h3>
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
      </div>
      <div className={styles.footer}>
        {price ? (
          <span className={`${styles.price} tabular`} title={item.priceSource ?? undefined}>
            {price}
          </span>
        ) : (
          <span className={styles.noPrice}>{t('catalog.noPrice')}</span>
        )}
        {item.priceSource ? (
          <span className={styles.priceSource}>
            {t('catalog.priceSource', { source: item.priceSource })}
          </span>
        ) : null}
      </div>
    </article>
  );
}
