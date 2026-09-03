import { createContext } from 'react';

export type ToastTone = 'success' | 'error' | 'info';

export interface ToastApi {
  show: (message: string, tone?: ToastTone) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);
