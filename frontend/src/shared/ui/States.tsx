import type { CSSProperties, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';
import styles from './States.module.css';

interface StateProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
}

export function EmptyState({ title, description, actions, icon = '◎' }: StateProps) {
  return (
    <div className={styles.state}>
      <div className={styles.icon} aria-hidden="true">
        {icon}
      </div>
      <div className={styles.title}>{title}</div>
      {description ? <p className={styles.description}>{description}</p> : null}
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
}

export function ErrorState({ detail, onRetry }: { detail?: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className={styles.state} role="alert">
      <div className={styles.icon} aria-hidden="true">
        ⚠
      </div>
      <div className={styles.title}>{t('errors.title')}</div>
      <p className={styles.description}>{detail ?? t('errors.generic')}</p>
      {onRetry ? (
        <div className={styles.actions}>
          <Button variant="secondary" onClick={onRetry}>
            {t('errors.retry')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function Skeleton({
  width,
  height = 16,
  style,
}: {
  width?: number | string;
  height?: number | string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={styles.skeleton}
      style={{ display: 'block', width: width ?? '100%', height, ...style }}
      aria-hidden="true"
    />
  );
}
