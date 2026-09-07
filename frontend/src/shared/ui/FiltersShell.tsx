import {
  ArrowDown,
  ArrowUp,
  LayoutGrid,
  Rows3,
  RotateCcw,
  SlidersHorizontal,
  X,
} from 'lucide-react';
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
                <X aria-hidden="true" />
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" onClick={onReset} className={styles.resetButton}>
            <RotateCcw size={15} aria-hidden="true" />
            {t('catalog.resetFilters')}
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
      <span className={`${styles.counter} tabular`}>{t('pagination.shown', { shown, total })}</span>
      {onOpenFilters ? (
        <Button
          variant="secondary"
          size="sm"
          className={styles.filtersButton}
          onClick={onOpenFilters}
        >
          <SlidersHorizontal size={15} aria-hidden="true" />
          {t('catalog.filters')}
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
          {order === 'asc' ? (
            <ArrowUp size={15} aria-hidden="true" />
          ) : (
            <ArrowDown size={15} aria-hidden="true" />
          )}
        </Button>
      </span>
    </div>
  );
}

/* The grid/table pair keeps its own names — every view switch in the app
 * imports them — but draws from the shared Lucide set like the rest of the
 * interface, instead of two hand-rolled SVGs at their own stroke weight. */
export function GridIcon() {
  return <LayoutGrid size={15} aria-hidden="true" />;
}

export function TableIcon() {
  return <Rows3 size={15} aria-hidden="true" />;
}
