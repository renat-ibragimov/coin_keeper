import { createContext, useContext } from 'react';

export const DonationDialogContext = createContext<(() => void) | null>(null);

export function useDonationDialog(): () => void {
  const openDonationDialog = useContext(DonationDialogContext);
  if (!openDonationDialog) {
    throw new Error('useDonationDialog must be used within DonationDialogProvider');
  }
  return openDonationDialog;
}
