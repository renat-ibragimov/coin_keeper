import { useId } from 'react';
import type { ReactNode, SelectHTMLAttributes } from 'react';

import styles from './Select.module.css';

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode;
  error?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}

export function Select({ label, error, hint, id, className, children, ...rest }: SelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <div className={styles.wrapper}>
      {label ? (
        <label className={styles.label} htmlFor={selectId}>
          {label}
        </label>
      ) : null}
      <select
        {...rest}
        id={selectId}
        className={[styles.select, error ? styles.invalid : '', className ?? '']
          .filter(Boolean)
          .join(' ')}
        aria-invalid={error ? true : undefined}
      >
        {children}
      </select>
      {error ? <div className={styles.error}>{error}</div> : null}
      {!error && hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
}
