import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { getAccessToken, setAccessToken, tryRefresh } from '@/shared/api/client';
import type { SessionOut, UserOut } from '@/shared/api/types';

import * as authApi from './api';
import { AuthContext } from './authContext';

const REMEMBER_KEY = 'ck-remember';

function rememberedSession(): boolean {
  try {
    return localStorage.getItem(REMEMBER_KEY) === '1';
  } catch {
    return false;
  }
}

function setRemembered(remember: boolean): void {
  try {
    if (remember) localStorage.setItem(REMEMBER_KEY, '1');
    else localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* convenience only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);

  // Silent session restore: the refresh token lives in an httpOnly cookie,
  // so the only way to know whether a session exists is to ask the server.
  // "Remember me" gates this — without it a returning visitor starts at the
  // sign-in screen even though the cookie may still be alive.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (rememberedSession() && (await tryRefresh()) && getAccessToken()) {
        try {
          const profile = await authApi.me();
          if (!cancelled) setUser(profile);
        } catch {
          setAccessToken(null);
        }
      }
      if (!cancelled) setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const acceptSession = useCallback((session: SessionOut) => {
    setAccessToken(session.tokens.accessToken);
    setUser(session.user);
  }, []);

  const signIn = useCallback(
    async (email: string, password: string, remember: boolean) => {
      const session = await authApi.login(email, password);
      setRemembered(remember);
      acceptSession(session);
    },
    [acceptSession],
  );

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setRemembered(false);
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, ready, signIn, acceptSession, signOut }),
    [user, ready, signIn, acceptSession, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
