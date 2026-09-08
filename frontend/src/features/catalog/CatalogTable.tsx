import { ArrowDown, ArrowUp, Check, ChevronsUpDown, CircleCheck, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CatalogListItem } from '@/shared/api/types';
import { coinTitle, seriesLabel } from '@/shared/lib/coinTitle';
import { formatUah } from '@/shared/lib/format';
import { Badge, Button, CoinImage } from '@/shared/ui';

import type { CatalogFilters, SortField } from './useCatalogFilters';
import styles from './CatalogTable.module.css';

interface CatalogTableProps {
  items: CatalogListItem[];
  filters: CatalogFilters;
  update: (changes: Partial<CatalogFilters>) => void;
}

type Align = 'left' | 'center' | 'right';

const ALIGN_CLASS: Record<Align, string> = {
  left: styles.alignLeft!,
  center: styles.alignCenter!,
  right: styles.alignRight!,
};

// The coin name is the row's anchor, so its header stays left with the
// thumbnail below it; every other column reads as a calm, centered strip
// even where its own values are right-aligned for scanning (docs/08-ui-map.md).
const COLUMNS: { key: string; sort?: SortField; align: Align }[] = [
  { key: 'tableCoin', sort: 'title', align: 'left' },
  { key: 'tableCountry', sort: 'country', align: 'center' },
  { key: 'tableSeries', sort: 'series', align: 'center' },
  { key: 'tableYear', sort: 'year', align: 'center' },
  { key: 'tableDenomination', sort: 'denomination', align: 'center' },
  { key: 'tablePurchase', sort: 'purchase', align: 'right' },
  { key: 'tablePrice', sort: 'price', align: 'right' },
  { key: 'tableActions', align: 'center' },
];

export function CatalogTable({ items, filters, update }: CatalogTableProps) {
  const { t, i18n } = useTranslation();

  function toggleSort(sort: SortField) {
    if (filters.sort === sort) {
      update({ order: filters.order === 'asc' ? 'desc' : 'asc' });
    } else {
      update({ sort, order: 'asc' });
    }
  }

  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th aria-hidden="true" className={styles.ownedHeader} />
            {COLUMNS.map((column) => {
              // The header itself is centered from "Країна" on — only the coin
              // name keeps a left header, matching its left-aligned content.
              const headerAlign = column.align === 'left' ? 'left' : 'center';
              return (
                <th key={column.key} className={ALIGN_CLASS[headerAlign]}>
                  {column.sort ? (
                    <button
                      type="button"
                      className={styles.sortButton}
                      onClick={() => toggleSort(column.sort!)}
                      aria-sort={
                        filters.sort === column.sort
                          ? filters.order === 'asc'
                            ? 'ascending'
                            : 'descending'
                          : undefined
                      }
                    >
                      {t(`catalog.${column.key}`)}
                      <span className={styles.sortIcon} aria-hidden="true">
                        {filters.sort === column.sort ? (
                          filters.order === 'asc' ? (
                            <ArrowUp size={13} />
                          ) : (
                            <ArrowDown size={13} />
                          )
                        ) : (
                          <ChevronsUpDown size={13} />
                        )}
                      </span>
                    </button>
                  ) : (
                    t(`catalog.${column.key}`)
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const owned = item.quantityOwned > 0;
            const addUrl = `/collection/coins/new?catalogItemId=${item.id}`;
            return (
              <tr
                key={item.id}
                className={[owned ? styles.ownedRow : '', item.isArchived ? styles.archivedRow : '']
                  .filter(Boolean)
                  .join(' ')}
              >
                <td className={styles.ownedCell}>
                  {owned ? (
                    <CircleCheck
                      size={16}
                      strokeWidth={1.75}
                      className={styles.ownedIcon}
                      role="img"
                      aria-label={t('catalog.badgeInCollection')}
                    />
                  ) : null}
                </td>
                <td className={ALIGN_CLASS.left}>
                  <div className={styles.coinCell}>
                    <CoinImage src={item.thumbnailUrl} alt="" className={styles.thumb} />
                    <span className={styles.coinInfo}>
                      <Link
                        to={`/catalog/${item.id}`}
                        className={`${styles.coinTitle} ${styles.rowLink}`}
                      >
                        {coinTitle(item, i18n.language)}
                      </Link>
                      {item.isOwn || item.isArchived ? (
                        <span className={styles.coinBadges}>
                          {item.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
                          {item.isArchived ? (
                            <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
                          ) : null}
                        </span>
                      ) : null}
                    </span>
                  </div>
                </td>
                <td className={`${ALIGN_CLASS.center} ${styles.secondary}`}>{item.country}</td>
                <td className={`${ALIGN_CLASS.center} ${styles.secondary}`}>
                  {seriesLabel(item, t) ?? '—'}
                </td>
                <td className={`${ALIGN_CLASS.center} tabular`}>{item.year}</td>
                <td className={ALIGN_CLASS.center}>{item.denomination?.label ?? '—'}</td>
                <td className={`${ALIGN_CLASS.right} tabular`}>
                  {owned ? (formatUah(item.purchaseTotalUah, i18n.language) ?? '—') : '—'}
                </td>
                <td className={`${ALIGN_CLASS.right} tabular`}>
                  {formatUah(item.marketPriceUah, i18n.language) ?? (
                    <span className={styles.muted}>{t('catalog.noPrice')}</span>
                  )}
                </td>
                <td className={`${ALIGN_CLASS.center} ${styles.actionsCell}`}>
                  {owned ? (
                    <div className={styles.ownedPill}>
                      <span className={styles.ownedStatus}>
                        <Check size={14} aria-hidden="true" />
                        {t('catalog.badgeInCollection')}
                      </span>
                      <Link
                        to={addUrl}
                        className={styles.addOneMore}
                        aria-label={t('catalog.addOneMore')}
                      >
                        +1
                      </Link>
                    </div>
                  ) : (
                    <Link to={addUrl}>
                      <Button size="sm" className={styles.addButton}>
                        <Plus size={14} aria-hidden="true" />
                        {t('catalog.addToCollection')}
                      </Button>
                    </Link>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
