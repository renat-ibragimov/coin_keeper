import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { Spinner } from './Spinner';
import styles from './Button.module.css';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'md' | 'sm';
  block?: boolean;
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  block = false,
  loading = false,
  disabled,
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  const className = [
    styles.button,
    styles[variant],
    styles[size],
    block ? styles.block : '',
    rest.className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button {...rest} type={type} className={className} disabled={disabled || loading}>
      {loading ? <Spinner size={16} /> : null}
      {children}
    </button>
  );
}
