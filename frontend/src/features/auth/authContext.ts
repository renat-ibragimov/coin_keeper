import { createContext } from 'react';

import type { SessionOut, UserOut } from '@/shared/api/types';

export interface AuthContextValue {
  user: UserOut | null;
  /** false while the initial silent session restore is still running */
  ready: boolean;
  signIn: (email: string, password: string, remember: boolean) => Promise<void>;
  acceptSession: (session: SessionOut) => void;
  /** Replace the cached profile after PATCH /auth/me. */
  updateUser: (user: UserOut) => void;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
