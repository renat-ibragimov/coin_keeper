import { useContext } from 'react';

import { ToastContext } from './toastContext';
import type { ToastApi } from './toastContext';

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  // Outside the provider (tests, isolated renders) a toast is simply dropped.
  return context ?? { show: () => {} };
}
