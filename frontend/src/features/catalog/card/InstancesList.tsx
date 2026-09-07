import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { DeleteInstanceDialog } from '@/features/collection/DeleteInstanceDialog';
import type { CatalogCollectionItem } from '@/shared/api/types';
import {
  currencySymbol,
  formatDate,
  formatMoney,
  formatNumber,
  formatUah,
} from '@/shared/lib/format';
import { Badge, Button, EmptyState, Skeleton } from '@/shared/ui';

import styles from './InstancesList.module.css';

interface InstancesListProps {
  items: CatalogCollectionItem[] | undefined;
  loading: boolean;
  /** Where the "add to collection" CTA in the empty state should lead. */
  addHref: string;
  /** The coin's own title, for the delete-confirmation text — instances
   *  carry no title of their own (docs/03-api-contract.md). */
  coinTitle: string;
}

/** "Мої екземпляри": one row per purchase of the current user. */
export function InstancesList({ items, loading, addHref, coinTitle }: InstancesListProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [deleting, setDeleting] = useState<CatalogCollectionItem | null>(null);

  if (loading) {
    return (
      <div className={styles.list} aria-busy="true">
        <Skeleton height={64} />
        <Skeleton height={64} />
      </div>
    );
  }
  if (!items || items.length === 0) {
    return (
      <EmptyState
        title={t('card.instancesEmpty')}
        actions={
          <Link to={addHref}>
            <Button variant="secondary">{t('catalog.addToCollection')}</Button>
          </Link>
        }
      />
    );
  }

  return (
    <>
      <ul className={styles.list}>
        {items.map((item) => {
          const foreign = item.purchaseCurrency !== null && item.purchaseCurrency !== 'UAH';
          const rate = foreign ? formatNumber(item.purchaseRateUah, locale, 4) : null;
          return (
            <li key={item.id} className={styles.row} data-testid="instance-row">
              <div className={styles.cell}>
                <span className={styles.cellLabel}>{t('card.instanceDate')}</span>
                <span className={`${styles.cellValue} tabular`}>
                  {item.acquisitionDate ? formatDate(item.acquisitionDate, locale) : '—'}
                  <span className={styles.secondary}>
                    {t('card.pieces', { count: item.quantity })}
                  </span>
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
              <div className={`${styles.cell} ${styles.actions}`}>
                <Link to={`/collection/coins/${item.id}/edit`}>
                  <Button variant="ghost" size="sm">
                    {t('common.edit')}
                  </Button>
                </Link>
                <Button variant="ghost" size="sm" onClick={() => setDeleting(item)}>
                  {t('common.delete')}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>

      <DeleteInstanceDialog
        item={deleting && { id: deleting.id, title: coinTitle, totalUah: deleting.totalUah }}
        onClose={() => setDeleting(null)}
      />
    </>
  );
}
