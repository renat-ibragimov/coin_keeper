import type { ReactNode } from 'react';

import styles from './PageHeader.module.css';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Buttons on the right (desktop) or under the title (phones). */
  actions?: ReactNode;
  /** Breadcrumbs or a back link above the title. */
  above?: ReactNode;
  /** "center" stacks title, subtitle and actions centered instead of the default left/right row. */
  align?: 'left' | 'center';
}

export function PageHeader({ title, subtitle, actions, above, align = 'left' }: PageHeaderProps) {
  return (
    <header className={styles.header}>
      {above ? <div className={styles.above}>{above}</div> : null}
      <div className={align === 'center' ? styles.rowCenter : styles.row}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>
    </header>
  );
}
