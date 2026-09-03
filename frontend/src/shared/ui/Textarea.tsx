import { useId } from 'react';
import type { ReactNode, TextareaHTMLAttributes } from 'react';

import inputStyles from './Input.module.css';
import styles from './Textarea.module.css';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode;
  error?: ReactNode;
  hint?: ReactNode;
}

export function Textarea({ label, error, hint, id, className, ...rest }: TextareaProps) {
  const autoId = useId();
  const textareaId = id ?? autoId;
  return (
    <div className={inputStyles.wrapper}>
      {label ? (
        <label className={inputStyles.label} htmlFor={textareaId}>
          {label}
        </label>
      ) : null}
      <textarea
        {...rest}
        id={textareaId}
        className={[
          inputStyles.input,
          styles.textarea,
          error ? inputStyles.invalid : '',
          className ?? '',
        ]
          .filter(Boolean)
          .join(' ')}
        aria-invalid={error ? true : undefined}
      />
      {error ? <div className={inputStyles.error}>{error}</div> : null}
      {!error && hint ? <div className={inputStyles.hint}>{hint}</div> : null}
    </div>
  );
}
