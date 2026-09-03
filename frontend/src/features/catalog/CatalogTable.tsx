import { useTranslation } from 'react-i18next';

import type { CatalogListItem } from '@/shared/api/types';
import { formatUah } from '@/shared/lib/format';
import { Badge } from '@/shared/ui';

import type { CatalogFilters, SortField } from './useCatalogFilters';
import styles from './CatalogTable.module.css';

interface CatalogTableProps {
  items: CatalogListItem[];
  filters: CatalogFilters;
  update: (changes: Partial<CatalogFilters>) => void;
}

const COLUMNS: { key: string; sort?: SortField }[] = [
  { key: 'tableCoin', sort: 'title' },
  { key: 'tableCountry', sort: 'country' },
  { key: 'tableSeries', sort: 'series' },
  { key: 'tableYear', sort: 'year' },
  { key: 'tableDenomination', sort: 'denomination' },
  { key: 'tableAvailability', sort: 'owned' },
  { key: 'tablePurchase', sort: 'purchase' },
  { key: 'tablePrice', sort: 'price' },
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
            {COLUMNS.map((column) => (
              <th key={column.key}>
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
                    {filters.sort === column.sort ? (
                      <span aria-hidden="true">{filters.order === 'asc' ? ' ↑' : ' ↓'}</span>
                    ) : null}
                  </button>
                ) : (
                  t(`catalog.${column.key}`)
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const owned = item.quantityOwned > 0;
            return (
              <tr key={item.id} className={item.isArchived ? styles.archivedRow : undefined}>
                <td>
                  <div className={styles.coinCell}>
                    {item.thumbnailUrl ? (
                      <img src={item.thumbnailUrl} alt="" loading="lazy" className={styles.thumb} />
                    ) : (
                      <span className={styles.thumbPlaceholder} aria-hidden="true">
                        ◎
                      </span>
                    )}
                    <span>
                      <span className={styles.coinTitle}>{item.title}</span>
                      <span className={styles.coinBadges}>
                        {item.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
                        {item.isArchived ? (
                          <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
                        ) : null}
                      </span>
                    </span>
                  </div>
                </td>
                <td>{item.country}</td>
                <td>{item.seriesName ?? '—'}</td>
                <td className="tabular">{item.year}</td>
                <td>{item.denomination ?? '—'}</td>
                <td>
                  {owned ? (
                    <Badge tone="success">
                      {t('catalog.badgeInCollection')}
                      {item.quantityOwned > 1 ? ` · ${item.quantityOwned}` : ''}
                    </Badge>
                  ) : (
                    <Badge tone="danger">{t('catalog.badgeMissing')}</Badge>
                  )}
                </td>
                <td className="tabular">
                  {owned ? (formatUah(item.purchaseTotalUah, i18n.language) ?? '—') : '—'}
                </td>
                <td className="tabular">
                  {formatUah(item.marketPriceUah, i18n.language) ?? (
                    <span className={styles.muted}>{t('catalog.noPrice')}</span>
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
