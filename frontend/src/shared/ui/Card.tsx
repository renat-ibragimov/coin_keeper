import type { HTMLAttributes, ReactNode } from 'react';

import styles from './Card.module.css';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
  children: ReactNode;
}

export function Card({ padded = true, className, children, ...rest }: CardProps) {
  return (
    <div
      {...rest}
      className={[styles.card, padded ? styles.padded : '', className ?? '']
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </div>
  );
}
