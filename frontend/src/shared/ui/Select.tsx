import { useId } from 'react';
import type { ReactNode, SelectHTMLAttributes } from 'react';

import styles from './Select.module.css';

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode;
  children: ReactNode;
}

export function Select({ label, id, className, children, ...rest }: SelectProps) {
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
        className={[styles.select, className ?? ''].filter(Boolean).join(' ')}
      >
        {children}
      </select>
    </div>
  );
}
