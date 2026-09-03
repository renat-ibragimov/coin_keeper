import { useTranslation } from 'react-i18next';

import type { CatalogCollectionItem } from '@/shared/api/types';
import {
  currencySymbol,
  formatDate,
  formatMoney,
  formatNumber,
  formatUah,
} from '@/shared/lib/format';
import { Badge, Skeleton } from '@/shared/ui';

import styles from './InstancesList.module.css';

interface InstancesListProps {
  items: CatalogCollectionItem[] | undefined;
  loading: boolean;
}

/** "Мої екземпляри та покупки": one row per purchase of the current user. */
export function InstancesList({ items, loading }: InstancesListProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  if (loading) {
    return (
      <div className={styles.list} aria-busy="true">
        <Skeleton height={64} />
        <Skeleton height={64} />
      </div>
    );
  }
  if (!items || items.length === 0) {
    return <p className={styles.empty}>{t('card.instancesEmpty')}</p>;
  }

  return (
    <ul className={styles.list}>
      {items.map((item) => {
        const foreign = item.purchaseCurrency !== null && item.purchaseCurrency !== 'UAH';
        const rate = foreign ? formatNumber(item.purchaseRateUah, locale, 4) : null;
        return (
          <li key={item.id} className={styles.row} data-testid="instance-row">
            <div className={styles.cell}>
              <span className={styles.cellLabel}>{t('card.instanceQuantity')}</span>
              <span className={styles.cellValue}>
                {t('card.pieces', { count: item.quantity })}
                {item.acquisitionDate ? (
                  <span className={`${styles.date} tabular`}>
                    {formatDate(item.acquisitionDate, locale)}
                  </span>
                ) : null}
              </span>
            </div>
            <div className={styles.cell}>
              <span className={styles.cellLabel}>{t('card.instanceSeller')}</span>
              <span className={styles.cellValue}>{item.seller || '—'}</span>
            </div>
            <div className={styles.cell}>
              <span className={styles.cellLabel}>{t('card.instancePrice')}</span>
              <span className={`${styles.cellValue} ${styles.price} tabular`}>
                {formatMoney(item.purchasePrice, item.purchaseCurrency, locale) ?? '—'}
                {foreign ? (
                  <span className={styles.priceUah}> = {formatUah(item.totalUah, locale)}</span>
                ) : null}
              </span>
            </div>
            <div className={styles.cell}>
              <span className={styles.cellLabel}>{t('card.instanceRate')}</span>
              <span className={`${styles.cellValue} tabular`}>
                {rate
                  ? t('card.rateFormat', { rate, symbol: currencySymbol(item.purchaseCurrency) })
                  : '—'}
              </span>
            </div>
            <div className={styles.cell}>
              <span className={styles.cellLabel}>{t('card.instanceGrade')}</span>
              <span className={styles.cellValue}>
                {item.grade ? <Badge>{item.grade}</Badge> : '—'}
              </span>
            </div>
            <div className={`${styles.cell} ${styles.notes}`}>
              <span className={styles.cellLabel}>{t('card.instanceNotes')}</span>
              <span className={styles.cellValue}>{item.notes || '—'}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
