import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CollectionItem } from '@/shared/api/types';
import { formatDate, formatMoney, formatUah } from '@/shared/lib/format';
import { Badge, Button, CoinImage } from '@/shared/ui';

import { instanceValuation } from './model';
import styles from './InstanceTable.module.css';

interface InstanceTableProps {
  items: CollectionItem[];
  onDelete: (item: CollectionItem) => void;
}

export function InstanceTable({ items, onDelete }: InstanceTableProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>{t('catalog.tableCoin')}</th>
            <th>{t('collection.grade')}</th>
            <th className={styles.number}>{t('collection.quantity')}</th>
            <th>{t('collection.purchaseDate')}</th>
            <th className={styles.number}>{t('collection.pricePerUnit')}</th>
            <th className={styles.number}>{t('collection.total')}</th>
            <th className={styles.number}>{t('collection.valuation')}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className={item.isArchived ? styles.archivedRow : undefined}>
              <td>
                <div className={styles.coinCell}>
                  <CoinImage src={item.thumbnailUrl} alt="" className={styles.thumb} />
                  <span>
                    <Link to={`/catalog/${item.catalogItemId}`} className={styles.coinTitle}>
                      {item.title}
                    </Link>
                    <span className={styles.coinMeta}>
                      {[item.country, String(item.year), item.denomination]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                    {item.isArchived ? (
                      <span className={styles.coinBadges}>
                        <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
                      </span>
                    ) : null}
                  </span>
                </div>
              </td>
              <td>{item.grade ? <Badge>{item.grade}</Badge> : '—'}</td>
              <td className={`${styles.number} tabular`}>{item.quantity}</td>
              <td className="tabular">{formatDate(item.purchaseDate, locale) ?? '—'}</td>
              <td className={`${styles.number} tabular`}>
                {formatMoney(item.price, item.currency, locale) ?? '—'}
              </td>
              <td className={`${styles.number} tabular`}>{formatUah(item.totalUah, locale)}</td>
              <td className={`${styles.number} tabular`}>
                {instanceValuation(item, locale) ?? (
                  <span className={styles.muted}>{t('catalog.noPrice')}</span>
                )}
              </td>
              <td className={styles.actions}>
                <Link to={`/collection/${item.id}/edit`}>
                  <Button variant="ghost" size="sm">
                    {t('common.edit')}
                  </Button>
                </Link>
                <Button variant="ghost" size="sm" onClick={() => onDelete(item)}>
                  {t('common.delete')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
