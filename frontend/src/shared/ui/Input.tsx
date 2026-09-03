import { useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';

import styles from './Input.module.css';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  error?: ReactNode;
  hint?: ReactNode;
}

export function Input({ label, error, hint, id, className, ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={styles.wrapper}>
      {label ? (
        <label className={styles.label} htmlFor={inputId}>
          {label}
        </label>
      ) : null}
      <input
        {...rest}
        id={inputId}
        className={[styles.input, error ? styles.invalid : '', className ?? '']
          .filter(Boolean)
          .join(' ')}
        aria-invalid={error ? true : undefined}
      />
      {error ? <div className={styles.error}>{error}</div> : null}
      {!error && hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
}
