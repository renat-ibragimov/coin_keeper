import { createContext, useContext } from 'react';

export type AuthDialogMode = 'login' | 'register';
export type AuthDialogPurpose = 'collection';
export type OpenAuthDialog = (
  mode?: AuthDialogMode,
  options?: { from?: string; purpose?: AuthDialogPurpose },
) => void;

export const AuthDialogContext = createContext<OpenAuthDialog | null>(null);

export function useAuthDialog(): OpenAuthDialog {
  const open = useContext(AuthDialogContext);
  if (!open) throw new Error('useAuthDialog must be used within AuthDialogProvider');
  return open;
}
