import { useCallback, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import styles from './Toast.module.css';
import { ToastContext } from './toastContext';
import type { ToastApi, ToastTone } from './toastContext';

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const TOAST_MS = 4000;

/** Short confirmations after an action ("Покупку збережено"). */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const show = useCallback((message: string, tone: ToastTone = 'success') => {
    const id = nextId.current++;
    setToasts((current) => [...current, { id, message, tone }]);
    setTimeout(() => setToasts((current) => current.filter((toast) => toast.id !== id)), TOAST_MS);
  }, []);

  const api = useMemo<ToastApi>(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className={styles.stack} aria-live="polite">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={[styles.toast, styles[toast.tone]].join(' ')}
            role="status"
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
