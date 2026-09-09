import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CollectionPosition } from '@/shared/api/types';
import { seriesLabel } from '@/shared/lib/coinTitle';
import { formatDate, formatUah } from '@/shared/lib/format';
import type { SortOrder } from '@/shared/ui';
import { Badge, cellAlign, clampTwoLines, CoinImage, DataTable, SortHeader } from '@/shared/ui';

import type { CollectionSort } from './useCollectionFilters';
import styles from './PositionTable.module.css';

interface PositionTableProps {
  items: CollectionPosition[];
  sort: CollectionSort;
  order: SortOrder;
  onSort: (sort: CollectionSort, order: SortOrder) => void;
}

// Widths of their own, for the same reason as the catalogue table: measured
// per page, the same series wrapped onto a different number of lines from one
// page to the next and rows changed height with it (docs/08-ui-map.md).
const COLUMNS: { key: string; sort: CollectionSort; className: string | undefined }[] = [
  { key: 'catalog.tableCoin', sort: 'title', className: styles.coinColumn },
  { key: 'catalog.tableCountry', sort: 'country', className: styles.countryColumn },
  { key: 'catalog.tableSeries', sort: 'series', className: styles.seriesColumn },
  { key: 'collection.quantity', sort: 'quantity', className: styles.quantityColumn },
  { key: 'collection.spent', sort: 'total', className: styles.moneyColumn },
  { key: 'collection.valuation', sort: 'valuation', className: styles.moneyColumn },
  { key: 'collection.lastAcquisition', sort: 'date', className: styles.dateColumn },
  { key: 'collection.grade', sort: 'grade', className: styles.gradeColumn },
];

export function PositionTable({ items, sort, order, onSort }: PositionTableProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  return (
    <DataTable minWidth={900}>
      <thead>
        <tr>
          {COLUMNS.map((column) => (
            <SortHeader
              key={column.key}
              label={t(column.key)}
              field={column.sort}
              sort={sort}
              order={order}
              onSort={onSort}
              className={column.className}
            />
          ))}
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.catalogItemId} className={item.isArchived ? styles.archivedRow : undefined}>
            <td>
              <div className={styles.coinCell}>
                <CoinImage src={item.thumbnailUrl} alt="" className={styles.thumb} />
                <span className={styles.coinInfo}>
                  <Link
                    to={`/catalog/${item.catalogItemId}`}
                    className={`${styles.coinTitle} ${styles.rowLink}`}
                  >
                    {item.title}
                  </Link>
                  {/* The badge rides on the meta line rather than under it: a
                   * line of its own made an archived position's row taller
                   * than every other (docs/08-ui-map.md). */}
                  <span className={styles.coinMeta}>
                    {[String(item.year), item.denomination].filter(Boolean).join(' · ')}
                    {item.isArchived ? (
                      <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
                    ) : null}
                  </span>
                </span>
              </div>
            </td>
            <td className={`${cellAlign.center} ${styles.secondary}`}>{item.country}</td>
            <td className={`${cellAlign.center} ${styles.secondary}`}>
              <span className={clampTwoLines}>{seriesLabel(item, t) ?? '—'}</span>
            </td>
            <td className={`${cellAlign.center} tabular`}>
              {t('catalog.quantity', { count: item.totalQuantity })}
            </td>
            <td className={`${cellAlign.center} tabular`}>
              {formatUah(item.totalSpendUah, locale)}
            </td>
            <td className={`${cellAlign.center} tabular`}>
              {item.marketValueUah !== null ? (
                formatUah(item.marketValueUah, locale)
              ) : (
                <span className={styles.muted}>{t('catalog.noPrice')}</span>
              )}
            </td>
            <td className={`${cellAlign.center} tabular`}>
              {item.lastAcquisitionDate ? formatDate(item.lastAcquisitionDate, locale) : '—'}
            </td>
            <td className={cellAlign.center}>
              {item.grades.length > 0 ? <Badge>{item.grades.join(' · ')}</Badge> : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </DataTable>
  );
}
