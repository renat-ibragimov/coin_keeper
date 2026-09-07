import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';
import { Select } from './Select';
import { Tabs } from './Tabs';
import type { TabOption } from './Tabs';
import styles from './FiltersShell.module.css';

export interface ActiveFilterChip {
  key: string;
  label: string;
  onRemove: () => void;
}

interface FiltersShellProps {
  /** Filter fields, laid out as a wrapping row with labels above each field. */
  children: ReactNode;
  activeFilters: ActiveFilterChip[];
  onReset: () => void;
}

/** The bordered filters box: the field row (as children) plus the active-filter chips. */
export function FiltersShell({ children, activeFilters, onReset }: FiltersShellProps) {
  const { t } = useTranslation();
  return (
    <div className={styles.panel}>
      <div className={styles.fields}>{children}</div>

      {activeFilters.length > 0 ? (
        <div className={styles.activeRow}>
          <span className={styles.activeLabel}>{t('catalog.activeFilters')}</span>
          <div className={styles.chips}>
            {activeFilters.map((chip) => (
              <button
                key={chip.key}
                type="button"
                className={styles.chip}
                onClick={chip.onRemove}
                aria-label={`${chip.label} — ${t('catalog.removeFilter')}`}
              >
                {chip.label}
                <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" onClick={onReset} className={styles.resetButton}>
            ↺ {t('catalog.resetFilters')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

interface SortOption {
  value: string;
  label: string;
}

interface FiltersToolbarProps<View extends string> {
  shown: number;
  total: number;
  view: View;
  viewOptions: TabOption<View>[];
  onViewChange: (view: View) => void;
  sort: string;
  sortOptions: SortOption[];
  onSortChange: (value: string) => void;
  order: 'asc' | 'desc';
  onOrderChange: () => void;
  /** Shows the mobile "Filters" trigger (the fields box collapses off-screen below it). */
  onOpenFilters?: () => void;
}

/** Below the filters box: the result count, the view switch, sort and direction. */
export function FiltersToolbar<View extends string>({
  shown,
  total,
  view,
  viewOptions,
  onViewChange,
  sort,
  sortOptions,
  onSortChange,
  order,
  onOrderChange,
  onOpenFilters,
}: FiltersToolbarProps<View>) {
  const { t } = useTranslation();
  return (
    <div className={styles.toolbar}>
      <span className={`${styles.counter} tabular`}>
        {t('pagination.shown', { shown, total })}
      </span>
      {onOpenFilters ? (
        <Button
          variant="secondary"
          size="sm"
          className={styles.filtersButton}
          onClick={onOpenFilters}
        >
          ☰ {t('catalog.filters')}
        </Button>
      ) : null}
      <Tabs<View>
        aria-label={t('catalog.viewLabel')}
        options={viewOptions}
        value={view}
        onChange={onViewChange}
      />
      <span className={styles.sortControls}>
        <Select
          value={sort}
          onChange={(event) => onSortChange(event.target.value)}
          aria-label={t('catalog.sort')}
        >
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Button
          variant="secondary"
          size="sm"
          onClick={onOrderChange}
          aria-label={order === 'asc' ? t('catalog.orderAsc') : t('catalog.orderDesc')}
          title={order === 'asc' ? t('catalog.orderAsc') : t('catalog.orderDesc')}
        >
          {order === 'asc' ? '↑' : '↓'}
        </Button>
      </span>
    </div>
  );
}

export function GridIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="8" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="1" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

export function TableIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="12" height="12" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
      <line x1="1" y1="5.3" x2="13" y2="5.3" stroke="currentColor" strokeWidth="1.1" />
      <line x1="1" y1="9.3" x2="13" y2="9.3" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}
