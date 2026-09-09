/* The cell classes of the shared table, kept out of DataTable.tsx so that file
 * exports components only (fast refresh). */
import styles from './DataTable.module.css';

/**
 * Cell alignment. Headers are centred site-wide (tokens.css), and so is every
 * value but a name: a column of right-aligned sums next to centred everything
 * else read as a table that could not make up its mind (owner, 2026-09-09).
 */
export const cellAlign = {
  left: '',
  center: styles.alignCenter!,
} as const;

/** Two-line window for a cell whose text can run long (a series, a material). */
export const clampTwoLines = styles.clamped!;
