import type { ReactNode } from 'react';

import styles from './PropertyList.module.css';

export interface PropertyRow {
  label: ReactNode;
  /** Rows with a null or empty value are skipped — only filled fields show. */
  value: ReactNode;
  key: string;
}

interface PropertyListProps {
  rows: PropertyRow[];
  /** Two columns on wide screens, one on narrow. */
  columns?: 1 | 2;
  className?: string;
}

export function PropertyList({ rows, columns = 1, className }: PropertyListProps) {
  const filled = rows.filter(
    (row) => row.value !== null && row.value !== undefined && row.value !== '',
  );
  if (filled.length === 0) return null;
  return (
    <dl
      className={[styles.list, columns === 2 ? styles.twoColumns : '', className ?? '']
        .filter(Boolean)
        .join(' ')}
    >
      {filled.map((row) => (
        <div key={row.key} className={styles.row}>
          <dt className={styles.label}>{row.label}</dt>
          <dd className={styles.value}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
