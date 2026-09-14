import { Pencil, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CatalogCard } from '@/shared/api/types';
import { imageSources } from '@/shared/lib/coinImage';
import { coinDenomination } from '@/shared/lib/coinDenomination';
import { coinMaterial } from '@/shared/lib/coinMaterial';
import { coinTitle } from '@/shared/lib/coinTitle';
import { Badge, CoinImage } from '@/shared/ui';

import styles from './SelectedCoin.module.css';

export type CoinSide = 'obverse' | 'reverse';

interface SelectedCoinProps {
  card: CatalogCard;
  /** Absent while editing a purchase: the coin of an existing one does not change. */
  onChange?: () => void;
  /** Overrides the catalog's own photo for one or both sides — a local
   *  preview of a just-picked file, or this exact instance's own uploaded
   *  photo (which the catalog card, aggregated across every purchase of the
   *  coin, does not necessarily carry). Absent a role, that side falls back
   *  to the catalog's picture. */
  photos?: Partial<Record<CoinSide, string | null>>;
  /** Present only where the owner may attach their own photo. */
  onPickPhoto?: (side: CoinSide) => void;
  /** Present only where a side with the owner's own photo may clear it. */
  onRemovePhoto?: (side: CoinSide) => void;
  /** Which sides in `photos` are the owner's own upload — `onRemovePhoto`
   *  only makes sense there, never on a side still showing the catalog's own
   *  picture. */
  ownPhoto?: Partial<Record<CoinSide, boolean>>;
}

/**
 * The coin a purchase is about: name, the line of facts under it, both sides.
 *
 * Shared by the "Додати" page and the edit page so the two cannot drift —
 * this is the view the owner signed off on, and adding a second copy of it
 * for the new page is how it would stop being the same view. `onPickPhoto`
 * turns each side into a control for the owner's own photo of that instance;
 * without it (a catalog page showing someone else's coin, say) the sides are
 * a plain picture, exactly as before.
 */
export function SelectedCoin({
  card,
  onChange,
  photos,
  onPickPhoto,
  onRemovePhoto,
  ownPhoto,
}: SelectedCoinProps) {
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
        {sides.map((side) => {
          const override = photos?.[side.key];
          const sources =
            override !== undefined && override !== null
              ? { src: override }
              : imageSources(side.image, 'card');
          return (
            <figure key={side.key} className={styles.photo}>
              <div className={styles.photoFrame}>
                <CoinImage {...sources} alt="" className={styles.photoImage} />
                {onPickPhoto ? (
                  <button
                    type="button"
                    className={styles.photoOverlay}
                    onClick={() => onPickPhoto(side.key)}
                  >
                    <Pencil size={16} aria-hidden="true" />
                    {t('card.changePhoto')}
                  </button>
                ) : null}
                {onPickPhoto ? (
                  <button
                    type="button"
                    className={styles.photoEdit}
                    aria-label={t('card.changePhoto')}
                    onClick={() => onPickPhoto(side.key)}
                  >
                    <Pencil size={13} aria-hidden="true" />
                  </button>
                ) : null}
                {onRemovePhoto && ownPhoto?.[side.key] ? (
                  <button
                    type="button"
                    className={styles.photoRemove}
                    aria-label={t('collectionPhoto.removePhoto')}
                    onClick={() => onRemovePhoto(side.key)}
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                ) : null}
              </div>
              <figcaption className={styles.photoLabel}>{side.label}</figcaption>
            </figure>
          );
        })}
      </div>
    </>
  );
}
