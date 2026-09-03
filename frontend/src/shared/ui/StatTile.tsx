import type { ReactNode } from 'react';

import styles from './StatTile.module.css';

interface StatTileProps {
  label: ReactNode;
  value: ReactNode;
  /** Secondary line under the value: a unit, a share, a note. */
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: 'neutral' | 'success' | 'danger';
}

/** A metric card: small caps label, big tabular number, optional hint. */
export function StatTile({ label, value, hint, icon, tone = 'neutral' }: StatTileProps) {
  return (
    <div className={styles.tile}>
      {icon ? (
        <span className={styles.icon} aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <div className={styles.body}>
        <div className={styles.label}>{label}</div>
        <div className={[styles.value, styles[tone], 'tabular'].join(' ')}>{value}</div>
        {hint ? <div className={styles.hint}>{hint}</div> : null}
      </div>
    </div>
  );
}
