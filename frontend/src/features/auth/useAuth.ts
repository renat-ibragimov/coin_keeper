import { useContext } from 'react';

import { AuthContext } from './authContext';
import type { AuthContextValue } from './authContext';

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
