import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CollectionItem } from '@/shared/api/types';
import { formatDate, formatMoney, formatUah } from '@/shared/lib/format';
import { Badge, Button, CoinImage } from '@/shared/ui';

import { instanceValuation } from './model';
import styles from './InstanceCard.module.css';

interface InstanceCardProps {
  item: CollectionItem;
  onDelete: (item: CollectionItem) => void;
}

export function InstanceCard({ item, onDelete }: InstanceCardProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const foreign = item.currency !== null && item.currency !== 'UAH';
  const valuation = instanceValuation(item, locale);
  const meta = [String(item.year), item.denomination].filter(Boolean).join(' · ');

  return (
    <article className={[styles.card, item.isArchived ? styles.archived : ''].join(' ')}>
      <Link to={`/catalog/${item.catalogItemId}`} className={styles.media} tabIndex={-1}>
        <CoinImage src={item.thumbnailUrl} alt="" className={styles.image} />
      </Link>
      <div className={styles.body}>
        <div className={styles.headline}>
          <h3 className={styles.title}>
            <Link to={`/catalog/${item.catalogItemId}`} className={styles.titleLink}>
              {item.title}
            </Link>
          </h3>
          {item.grade ? <Badge>{item.grade}</Badge> : null}
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
            <dd className="tabular">{t('catalog.quantity', { count: item.quantity })}</dd>
          </div>
          <div className={styles.fact}>
            <dt>{t('collection.purchaseDate')}</dt>
            <dd className="tabular">{formatDate(item.purchaseDate, locale) ?? '—'}</dd>
          </div>
          <div className={styles.fact}>
            <dt>{t('collection.pricePerUnit')}</dt>
            <dd className="tabular">
              {formatMoney(item.price, item.currency, locale) ?? '—'}
              {foreign ? (
                <span className={styles.muted}> = {formatUah(item.totalUah, locale)}</span>
              ) : null}
            </dd>
          </div>
          <div className={styles.fact}>
            <dt>{t('collection.valuation')}</dt>
            <dd className="tabular">
              {valuation ?? <span className={styles.muted}>{t('catalog.noPrice')}</span>}
            </dd>
          </div>
        </dl>
        {item.notes ? <p className={styles.notes}>{item.notes}</p> : null}
      </div>
      <div className={styles.footer}>
        <Link to={`/collection/${item.id}/edit`}>
          <Button variant="secondary" size="sm">
            {t('common.edit')}
          </Button>
        </Link>
        <Button variant="ghost" size="sm" onClick={() => onDelete(item)}>
          {t('common.delete')}
        </Button>
      </div>
    </article>
  );
}
