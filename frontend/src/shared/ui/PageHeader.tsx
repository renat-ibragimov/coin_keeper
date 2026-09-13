import { ArrowLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';
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
  /** A back button to the left of the title (center layouts only). */
  onBack?: () => void;
}

export function PageHeader({
  title,
  subtitle,
  actions,
  above,
  align = 'left',
  onBack,
}: PageHeaderProps) {
  const { t } = useTranslation();
  const titleBlock = (
    <div>
      <h1 className={styles.title}>{title}</h1>
      {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
    </div>
  );

  return (
    <header className={styles.header}>
      {above ? <div className={styles.above}>{above}</div> : null}
      {align === 'center' && onBack ? (
        <div className={styles.titleBar}>
          <Button variant="ghost" size="sm" onClick={onBack} className={styles.backButton}>
            <ArrowLeft size={15} aria-hidden="true" />
            {t('common.back')}
          </Button>
          <div className={styles.titleCellCenter}>{titleBlock}</div>
        </div>
      ) : (
        <div className={align === 'center' ? styles.rowCenter : styles.row}>
          {titleBlock}
          {actions ? <div className={styles.actions}>{actions}</div> : null}
        </div>
      )}
      {align === 'center' && onBack && actions ? (
        <div className={`${styles.actions} ${styles.actionsCenter}`}>{actions}</div>
      ) : null}
    </header>
  );
}
