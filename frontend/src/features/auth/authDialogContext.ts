import { createContext, useContext } from 'react';

export type AuthDialogMode = 'login' | 'register' | 'forgot-password' | 'check-email';
export interface AuthDialogOptions {
  from?: string;
  purpose?: AuthDialogPurpose;
  reason?: 'expired';
  email?: string;
  google?: string;
  returnState?: { from?: string };
}
export type AuthDialogPurpose = 'collection';
export type OpenAuthDialog = (mode?: AuthDialogMode, options?: AuthDialogOptions) => void;

export const AuthDialogContext = createContext<OpenAuthDialog | null>(null);

export function useAuthDialog(): OpenAuthDialog {
  const open = useContext(AuthDialogContext);
  if (!open) throw new Error('useAuthDialog must be used within AuthDialogProvider');
  return open;
}
