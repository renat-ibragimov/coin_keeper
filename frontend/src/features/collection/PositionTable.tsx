import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CollectionPosition } from '@/shared/api/types';
import { formatDate, formatUah } from '@/shared/lib/format';
import { Badge, CoinImage } from '@/shared/ui';

import styles from './PositionTable.module.css';

interface PositionTableProps {
  items: CollectionPosition[];
}

export function PositionTable({ items }: PositionTableProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>{t('catalog.tableCoin')}</th>
            <th>{t('catalog.tableCountry')}</th>
            <th>{t('catalog.tableSeries')}</th>
            <th className={styles.number}>{t('collection.quantity')}</th>
            <th className={styles.number}>{t('collection.spent')}</th>
            <th className={styles.number}>{t('collection.valuation')}</th>
            <th>{t('collection.lastAcquisition')}</th>
            <th>{t('collection.grade')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.catalogItemId} className={item.isArchived ? styles.archivedRow : undefined}>
              <td>
                <div className={styles.coinCell}>
                  <CoinImage src={item.thumbnailUrl} alt="" className={styles.thumb} />
                  <span>
                    <Link
                      to={`/catalog/${item.catalogItemId}`}
                      className={`${styles.coinTitle} ${styles.rowLink}`}
                    >
                      {item.title}
                    </Link>
                    <span className={styles.coinMeta}>
                      {[String(item.year), item.denomination].filter(Boolean).join(' · ')}
                    </span>
                    {item.isArchived ? (
                      <span className={styles.coinBadges}>
                        <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
                      </span>
                    ) : null}
                  </span>
                </div>
              </td>
              <td className={styles.secondary}>{item.country}</td>
              <td className={styles.secondary}>{item.seriesName ?? '—'}</td>
              <td className={`${styles.number} tabular`}>
                {t('catalog.quantity', { count: item.totalQuantity })}
              </td>
              <td className={`${styles.number} tabular`}>{formatUah(item.totalSpendUah, locale)}</td>
              <td className={`${styles.number} tabular`}>
                {item.marketValueUah !== null ? (
                  formatUah(item.marketValueUah, locale)
                ) : (
                  <span className={styles.muted}>{t('catalog.noPrice')}</span>
                )}
              </td>
              <td className="tabular">
                {item.lastAcquisitionDate ? formatDate(item.lastAcquisitionDate, locale) : '—'}
              </td>
              <td>{item.grades.length > 0 ? <Badge>{item.grades.join(' · ')}</Badge> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
