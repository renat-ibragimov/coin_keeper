import styles from './Spinner.module.css';

export function Spinner({ size = 24 }: { size?: number }) {
  return (
    <span
      /* motion-essential: a spinner that stops spinning under
         prefers-reduced-motion says nothing at all (tokens.css). */
      className={`${styles.spinner} motion-essential`}
      style={{ width: size, height: size, borderWidth: Math.max(2, size / 10) }}
      role="status"
      aria-label="Loading"
    />
  );
}
