import { Check, ExternalLink, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CatalogListItem } from '@/shared/api/types';
import { imageSources } from '@/shared/lib/coinImage';
import { coinMaterial, shortMaterial } from '@/shared/lib/coinMaterial';
import { coinTitle, seriesLabel } from '@/shared/lib/coinTitle';
import { formatUah } from '@/shared/lib/format';
import { priceSourceLabel } from '@/shared/lib/priceSource';
import { Badge, Button, CoinImage } from '@/shared/ui';

import styles from './CoinCard.module.css';

function CoinImages({ item }: { item: CatalogListItem }) {
  const obverse = imageSources(item.obverseImage, 'list');
  const reverse = imageSources(item.reverseImage, 'list');
  const shown = [obverse, reverse].filter((side) => side.src);
  // With one side stored, or none at all, a single frame spans the media area;
  // CoinImage decides on its own whether it shows a photo or the placeholder.
  if (shown.length < 2) {
    return <CoinImage {...(shown[0] ?? { src: null })} alt="" className={styles.imageSingle} />;
  }
  return (
    <>
      <CoinImage {...obverse} alt="" className={styles.image} />
      <CoinImage {...reverse} alt="" className={styles.image} />
    </>
  );
}

interface CoinCardProps {
  item: CatalogListItem;
  /**
   * Where "add to collection" / "+1" return to after the purchase form is
   * saved or cancelled (router state, read back by PurchaseFormPage).
   * Without it, the form falls back to the coin's own detail page — fine
   * from the catalog itself, but a series or missing-coins listing wants
   * the visitor back where they were, not bounced to `/catalog/:id`.
   */
  backTo?: string;
  /**
   * Series id lookup by display name. `CatalogListItem` only carries the
   * series' name (already resolved to the interface locale, docs/03-api-contract.md),
   * not its id — the caller builds this from the series list it already
   * fetches for the filters panel, so the series line can link to the full
   * series page without a new request or a made-up field. Absent (or no
   * match) just falls back to plain text, unchanged.
   */
  seriesIdByName?: Record<string, number>;
}

/**
 * The tile card for a catalog item: the one shared shape for a coin in a
 * grid, used identically by the catalog, a series and the missing-coins
 * list — same image treatment, same fixed-height title, same collection
 * state footer, so all three never drift apart into subtly different cards
 * again (docs/08-ui-map.md).
 */
export function CoinCard({ item, backTo, seriesIdByName }: CoinCardProps) {
  const { t, i18n } = useTranslation();
  const price = formatUah(item.marketPriceUah, i18n.language);
  const owned = item.quantityOwned > 0;
  const title = coinTitle(item, i18n.language);
  const series = seriesLabel(item, t);
  const material = coinMaterial(item);
  const cardUrl = `/catalog/${item.id}`;
  const addUrl = `/collection/coins/new?catalogItemId=${item.id}`;
  const addState = backTo ? { from: backTo } : undefined;
  const sourceLabel = priceSourceLabel(item.priceSource, t);

  return (
    <article
      className={[styles.card, owned ? styles.owned : '', item.isArchived ? styles.archived : '']
        .filter(Boolean)
        .join(' ')}
    >
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
        {/* Face value and metal on one line: two coins that look alike in the
         * grid differ in price mostly by what they are made of. The material
         * sits right of the face value, shortened to two words so it never
         * takes the whole line; either half may be missing — the record
         * simply says nothing (docs/08-ui-map.md). */}
        {item.denomination || material ? (
          <div className={styles.specs}>
            <span className={styles.denomination}>{item.denomination?.label ?? ''}</span>
            {material ? (
              <span className={styles.material} title={material}>
                {shortMaterial(material)}
              </span>
            ) : null}
          </div>
        ) : null}
        {/* Fixed two-line window (CSS): every card's meta line starts at the
         * same height regardless of title length (docs/08-ui-map.md). */}
        <h3 className={styles.title} title={title}>
          <Link to={cardUrl} className={`${styles.titleLink} ${styles.titleLinkStretched}`}>
            {title}
          </Link>
        </h3>
        <div className={styles.meta}>
          {item.country} · <span className="tabular">{item.year}</span>
        </div>
        {series ? (
          item.seriesName && seriesIdByName?.[item.seriesName] != null ? (
            <Link
              to={`/collection/series/${seriesIdByName[item.seriesName]}`}
              className={styles.seriesLink}
            >
              {series}
            </Link>
          ) : (
            <div className={styles.series}>{series}</div>
          )
        ) : null}
        {/* No negative "missing" badge: the footer below already says it —
         * the gold CTA for a coin that's missing, the green row for one
         * that isn't (docs/08-ui-map.md). */}
      </div>
      <div className={styles.footer}>
        {price ? (
          <span className={`${styles.price} tabular`}>{price}</span>
        ) : (
          <span className={styles.noPrice}>{t('catalog.noPrice')}</span>
        )}
        {sourceLabel ? (
          item.sourceUrl ? (
            <a
              className={styles.priceSourceLink}
              href={item.sourceUrl}
              target="_blank"
              rel="noreferrer"
            >
              {sourceLabel}
              <ExternalLink size={11} aria-hidden="true" />
            </a>
          ) : (
            <span className={styles.priceSource}>{sourceLabel}</span>
          )
        ) : null}
      </div>
      <div className={styles.action}>
        {owned ? (
          <div className={styles.ownedRow}>
            <span className={styles.ownedStatus}>
              <Check size={15} aria-hidden="true" />
              {t('catalog.badgeInCollection')}
            </span>
            <Link
              to={addUrl}
              state={addState}
              className={styles.addOneMore}
              aria-label={t('catalog.addOneMore')}
            >
              +1
            </Link>
          </div>
        ) : (
          <Link to={addUrl} state={addState}>
            <Button block>
              <Plus size={16} aria-hidden="true" />
              {t('catalog.addToCollection')}
            </Button>
          </Link>
        )}
      </div>
    </article>
  );
}
