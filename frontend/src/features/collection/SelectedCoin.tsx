import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CatalogCard } from '@/shared/api/types';
import { imageSources } from '@/shared/lib/coinImage';
import { coinDenomination } from '@/shared/lib/coinDenomination';
import { coinMaterial } from '@/shared/lib/coinMaterial';
import { coinTitle } from '@/shared/lib/coinTitle';
import { Badge, CoinImage } from '@/shared/ui';

import styles from './SelectedCoin.module.css';

interface SelectedCoinProps {
  card: CatalogCard;
  /** Absent while editing a purchase: the coin of an existing one does not change. */
  onChange?: () => void;
}

/**
 * The coin a purchase is about: name, the line of facts under it, both sides.
 *
 * Shared by the "Додати" page and the edit page so the two cannot drift —
 * this is the view the owner signed off on, and adding a second copy of it
 * for the new page is how it would stop being the same view.
 */
export function SelectedCoin({ card, onChange }: SelectedCoinProps) {
  const { t, i18n } = useTranslation();
  const sides = [
    { key: 'obverse' as const, image: card.obverseImage, label: t('card.obverse') },
    { key: 'reverse' as const, image: card.reverseImage, label: t('card.reverse') },
  ];

  return (
    <>
      <div className={styles.coinHeader}>
        <div className={styles.coinBadges}>
          {card.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
          {card.isArchived ? <Badge tone="warning">{t('catalog.badgeArchived')}</Badge> : null}
        </div>
        <Link to={`/catalog/${card.id}`} className={styles.coinTitle}>
          {coinTitle(card, i18n.language)}
        </Link>
        <div className={styles.coinMeta}>
          {[
            card.country,
            card.seriesName,
            String(card.year),
            coinDenomination(card),
            coinMaterial(card),
          ]
            .filter(Boolean)
            .join(' · ')}
        </div>
        {onChange ? (
          <button type="button" className={styles.changeItem} onClick={onChange}>
            {t('purchase.changeItem')}
          </button>
        ) : null}
      </div>

      <div className={styles.photos}>
        {sides.map((side) => (
          <figure key={side.key} className={styles.photo}>
            <CoinImage {...imageSources(side.image, 'card')} alt="" className={styles.photoImage} />
            <figcaption className={styles.photoLabel}>{side.label}</figcaption>
          </figure>
        ))}
      </div>
    </>
  );
}
