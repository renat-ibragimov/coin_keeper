import type { HTMLAttributes, ReactNode } from 'react';

import styles from './Card.module.css';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
  /**
   * "raised" (the default) is a content card that sits above the page;
   * "panel" is a structural frame built into it — filters, charts, tables,
   * the dense overview columns. The two differ in surface, radius and
   * elevation only (docs/08-ui-map.md).
   */
  variant?: 'raised' | 'panel';
  children: ReactNode;
}

export function Card({
  padded = true,
  variant = 'raised',
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      {...rest}
      className={[
        variant === 'panel' ? styles.panel : styles.card,
        padded ? styles.padded : '',
        className ?? '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </div>
  );
}
