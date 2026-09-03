import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import styles from './Lightbox.module.css';

interface LightboxProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name of the dialog, e.g. "Аверс — Дельфін". */
  label: string;
  children: ReactNode;
}

/** A full-screen overlay for one enlarged image. Escape and a click outside close it. */
export function Lightbox({ open, onClose, label, children }: LightboxProps) {
  const { t } = useTranslation();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className={styles.overlay} onClick={onClose} data-testid="lightbox">
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className={styles.close}
          onClick={onClose}
          aria-label={t('common.close')}
          autoFocus
        >
          ✕
        </button>
        <div className={styles.caption}>{label}</div>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
