import { useId } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';

import styles from './Input.module.css';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  error?: ReactNode;
  hint?: ReactNode;
  /**
   * A control drawn inside the field at its right edge (a reveal button, a
   * unit). It is anchored to the input itself, so a hint or an error under
   * the field never pushes it around.
   */
  trailing?: ReactNode;
}

export function Input({ label, error, hint, trailing, id, className, ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const input = (
    <input
      {...rest}
      id={inputId}
      className={[
        styles.input,
        error ? styles.invalid : '',
        trailing ? styles.withTrailing : '',
        className ?? '',
      ]
        .filter(Boolean)
        .join(' ')}
      aria-invalid={error ? true : undefined}
    />
  );
  return (
    <div className={styles.wrapper}>
      {label ? (
        <label className={styles.label} htmlFor={inputId}>
          {label}
        </label>
      ) : null}
      {trailing ? (
        <div className={styles.control} data-testid="input-control">
          {input}
          <span className={styles.trailing}>{trailing}</span>
        </div>
      ) : (
        input
      )}
      {error ? <div className={styles.error}>{error}</div> : null}
      {!error && hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
}
