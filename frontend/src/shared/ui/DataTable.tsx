import type { ReactNode } from 'react';

import styles from './DataTable.module.css';

interface DataTableProps {
  /** Below this the panel scrolls sideways instead of squeezing the columns. */
  minWidth: number;
  children: ReactNode;
}

/**
 * The site's one table: a structural panel with a header strip and a row
 * rhythm shared by every listing (docs/08-ui-map.md). Columns, and the look of
 * what sits inside a cell, stay with the feature that owns the data.
 */
export function DataTable({ minWidth, children }: DataTableProps) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table} style={{ minWidth }}>
        {children}
      </table>
    </div>
  );
}

/**
 * One glyph for all three sort states: the pair of chevrons never changes shape
 * or size, only which half is lit. A single arrow over the sorted column and a
 * double chevron over the rest made one header visibly unlike its neighbours
 * (owner, 2026-09-09). The geometry is lucide's own `chevrons-up-down`, so it
 * sits with the other icons in the interface.
 */
function SortIcon({ direction }: { direction: SortOrder | null }) {
  return (
    <svg
      className={styles.sortIcon}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m7 9 5-5 5 5" className={direction === 'asc' ? styles.sortHalfActive : undefined} />
      <path
        d="m7 15 5 5 5-5"
        className={direction === 'desc' ? styles.sortHalfActive : undefined}
      />
    </svg>
  );
}

export type SortOrder = 'asc' | 'desc';

const SORT_STATE = { asc: 'ascending', desc: 'descending' } as const;

interface SortHeaderProps<TField extends string> {
  label: string;
  field: TField;
  sort: TField;
  order: SortOrder;
  /** Called with the column's own field and the order it should take. */
  onSort: (sort: TField, order: SortOrder) => void;
  className?: string | undefined;
}

/**
 * A sortable column header. Clicking the column that already sorts the listing
 * flips its direction; any other column starts ascending — the same rule in
 * every table.
 */
export function SortHeader<TField extends string>({
  label,
  field,
  sort,
  order,
  onSort,
  className,
}: SortHeaderProps<TField>) {
  const active = sort === field;
  return (
    <th className={className} aria-sort={active ? SORT_STATE[order] : 'none'}>
      <button
        type="button"
        className={styles.sortButton}
        onClick={() => onSort(field, active && order === 'asc' ? 'desc' : 'asc')}
      >
        {label}
        <SortIcon direction={active ? order : null} />
      </button>
    </th>
  );
}
