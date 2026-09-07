import { CircleAlert, CircleDashed } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';
import { Card } from './Card';
import styles from './States.module.css';

interface StateProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  /** "card" puts the state on a surface-raised card — the whole-page empty
   *  states (Огляд, Мої монети, Серії, Гроші). In-content states (nothing
   *  found after a filter/search) stay "plain", the default. */
  variant?: 'plain' | 'card';
}

export function EmptyState({
  title,
  description,
  actions,
  icon = <CircleDashed strokeWidth={1.75} />,
  variant = 'plain',
}: StateProps) {
  const content = (
    <div className={styles.state}>
      <div className={styles.icon} aria-hidden="true">
        {icon}
      </div>
      <div className={styles.title}>{title}</div>
      {description ? <p className={styles.description}>{description}</p> : null}
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
  return variant === 'card' ? <Card>{content}</Card> : content;
}

interface ErrorStateProps {
  /** Overrides the generic "something went wrong" heading, e.g. "Item not found". */
  title?: ReactNode;
  detail?: ReactNode;
  onRetry?: () => void;
  actions?: ReactNode;
}

export function ErrorState({ title, detail, onRetry, actions }: ErrorStateProps) {
  const { t } = useTranslation();
  return (
    <div className={styles.state} role="alert">
      <div className={styles.icon} aria-hidden="true">
        <CircleAlert strokeWidth={1.75} />
      </div>
      <div className={styles.title}>{title ?? t('errors.title')}</div>
      <p className={styles.description}>{detail ?? t('errors.generic')}</p>
      {onRetry || actions ? (
        <div className={styles.actions}>
          {onRetry ? (
            <Button variant="secondary" onClick={onRetry}>
              {t('errors.retry')}
            </Button>
          ) : null}
          {actions}
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
