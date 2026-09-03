import styles from './Spinner.module.css';

export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <span
      className={styles.spinner}
      style={{ width: size, height: size, borderWidth: Math.max(2, size / 10) }}
      role="status"
      aria-label="Loading"
    />
  );
}
