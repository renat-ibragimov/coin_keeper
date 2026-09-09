import { Check, CircleCheck, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { CatalogListItem } from '@/shared/api/types';
import { coinMaterial } from '@/shared/lib/coinMaterial';
import { coinTitle, seriesLabel } from '@/shared/lib/coinTitle';
import { formatUah } from '@/shared/lib/format';
import type { SortOrder } from '@/shared/ui';
import {
  Badge,
  Button,
  cellAlign,
  clampTwoLines,
  CoinImage,
  DataTable,
  SortHeader,
} from '@/shared/ui';

import type { CatalogFilters, SortField } from './useCatalogFilters';
import styles from './CatalogTable.module.css';

interface CatalogTableProps {
  items: CatalogListItem[];
  filters: CatalogFilters;
  update: (changes: Partial<CatalogFilters>) => void;
}

// Every column carries its own width. Left to itself the table measures each
// page's own text, so the same series wrapped onto two lines on one page and
// three on the next, and rows changed height from page to page. The actions
// column is measured in pixels rather than in a share of the table: it holds a
// button in one state and a status pill in the other (docs/08-ui-map.md).
const COLUMNS: { key: string; sort?: SortField; className?: string }[] = [
  { key: 'tableCoin', sort: 'title', className: styles.coinColumn },
  { key: 'tableCountry', sort: 'country', className: styles.countryColumn },
  { key: 'tableSeries', sort: 'series', className: styles.seriesColumn },
  { key: 'tableYear', sort: 'year', className: styles.yearColumn },
  { key: 'tableDenomination', sort: 'denomination', className: styles.denominationColumn },
  { key: 'tableMaterial', sort: 'material', className: styles.materialColumn },
  { key: 'tablePurchase', sort: 'purchase', className: styles.moneyColumn },
  { key: 'tablePrice', sort: 'price', className: styles.moneyColumn },
  { key: 'tableActions', className: styles.actionsColumn },
];

export function CatalogTable({ items, filters, update }: CatalogTableProps) {
  const { t, i18n } = useTranslation();

  function sortBy(sort: SortField, order: SortOrder) {
    update({ sort, order });
  }

  return (
    <DataTable minWidth={980}>
      <thead>
        <tr>
          <th aria-hidden="true" className={styles.ownedHeader} />
          {COLUMNS.map((column) =>
            column.sort ? (
              <SortHeader
                key={column.key}
                label={t(`catalog.${column.key}`)}
                field={column.sort}
                sort={filters.sort}
                order={filters.order}
                onSort={sortBy}
                className={column.className}
              />
            ) : (
              <th key={column.key} className={column.className}>
                {t(`catalog.${column.key}`)}
              </th>
            ),
          )}
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const owned = item.quantityOwned > 0;
          const material = coinMaterial(item);
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
              <td>
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
              <td className={`${cellAlign.center} ${styles.secondary}`}>{item.country}</td>
              <td className={`${cellAlign.center} ${styles.secondary}`}>
                <span className={clampTwoLines}>{seriesLabel(item, t) ?? '—'}</span>
              </td>
              <td className={`${cellAlign.center} tabular`}>{item.year}</td>
              <td className={cellAlign.center}>{item.denomination?.label ?? '—'}</td>
              <td className={`${cellAlign.center} ${styles.secondary}`}>
                {material ? (
                  <span className={clampTwoLines} title={material}>
                    {material}
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className={`${cellAlign.center} tabular`}>
                {owned ? (formatUah(item.purchaseTotalUah, i18n.language) ?? '—') : '—'}
              </td>
              <td className={`${cellAlign.center} tabular`}>
                {formatUah(item.marketPriceUah, i18n.language) ?? (
                  <span className={styles.muted}>{t('catalog.noPrice')}</span>
                )}
              </td>
              <td className={`${cellAlign.center} ${styles.actionsCell}`}>
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
    </DataTable>
  );
}
