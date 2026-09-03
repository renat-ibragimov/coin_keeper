import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import styles from './Breadcrumbs.module.css';

export interface Crumb {
  label: ReactNode;
  /** Omit for the current page. */
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t('common.breadcrumbs')} className={styles.nav}>
      <ol className={styles.list}>
        {items.map((item, index) => (
          <li key={index} className={styles.item}>
            {item.to ? (
              <Link to={item.to} className={styles.link}>
                {item.label}
              </Link>
            ) : (
              <span aria-current="page">{item.label}</span>
            )}
            {index < items.length - 1 ? (
              <span className={styles.separator} aria-hidden="true">
                /
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}
