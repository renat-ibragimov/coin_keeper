import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import {
  ApiError,
  getAccessToken,
  onAccessTokenChange,
  setAccessToken,
  tryRefresh,
} from '@/shared/api/client';
import type { SessionOut, UserOut } from '@/shared/api/types';

import * as authApi from './api';
import { AuthContext } from './authContext';
import { GOOGLE_POPUP_FLOW_KEY } from './googlePopup';
import { setDraftOwner, retainSessionDrafts } from './sessionDrafts';
import { saveAuthReturn } from './authReturn';

const REMEMBER_KEY = 'ck-remember';
/** Tells the viewer's other tabs about a voluntary sign-out. */
const AUTH_CHANNEL = 'ck-auth';

/**
 * The Google popup mounts the whole app but only reports back to its opener;
 * a refresh of its own would race the opener's with the same cookie.
 */
function insideGooglePopup(): boolean {
  try {
    return sessionStorage.getItem(GOOGLE_POPUP_FLOW_KEY) !== null;
  } catch {
    return false;
  }
}

function rememberedSession(): boolean {
  try {
    return (
      localStorage.getItem(REMEMBER_KEY) === '1' || sessionStorage.getItem(REMEMBER_KEY) === '1'
    );
  } catch {
    return false;
  }
}

function persistAcrossVisits(): boolean {
  try {
    return localStorage.getItem(REMEMBER_KEY) === '1';
  } catch {
    return false;
  }
}

function setRemembered(remember: boolean): void {
  try {
    sessionStorage.setItem(REMEMBER_KEY, '1');
    if (remember) localStorage.setItem(REMEMBER_KEY, '1');
    else localStorage.removeItem(REMEMBER_KEY);
  } catch {
    /* convenience only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);

  const [sessionEnd, setSessionEnd] = useState<'expired' | 'signed-out' | null>(null);
  const currentUser = useRef<UserOut | null>(null);
  const signingOut = useRef(false);
  const acknowledgeSessionEnd = useCallback(() => setSessionEnd(null), []);

  useEffect(
    () =>
      onAccessTokenChange((token) => {
        if (token || !currentUser.current || signingOut.current) return;
        retainSessionDrafts();
        currentUser.current = null;
        setUser(null);
        setSessionEnd('expired');
      }),
    [],
  );

  // Restore remembered sessions across visits, or temporary ones within this tab.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!insideGooglePopup() && rememberedSession() && (await tryRefresh()) && getAccessToken()) {
        try {
          const profile = await authApi.me();
          if (!cancelled) {
            currentUser.current = profile;
            setDraftOwner(profile.id);
            setUser(profile);
          }
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

  const acceptSession = useCallback((session: SessionOut, remember?: boolean) => {
    setRemembered(remember ?? persistAcrossVisits());
    setDraftOwner(session.user.id);
    currentUser.current = session.user;
    setSessionEnd(null);
    setAccessToken(session.tokens.accessToken);
    setUser(session.user);
  }, []);

  const completeGoogleSession = useCallback(async (remember?: boolean) => {
    if (!(await tryRefresh())) throw new Error('Google session refresh failed');
    const profile = await authApi.me();
    setRemembered(remember ?? persistAcrossVisits());
    setDraftOwner(profile.id);
    currentUser.current = profile;
    setSessionEnd(null);
    setUser(profile);
  }, []);

  const signIn = useCallback(
    async (email: string, password: string, remember: boolean) => {
      const session = await authApi.login(email, password);
      acceptSession(session, remember);
    },
    [acceptSession],
  );

  /** Everything a voluntary sign-out clears in a tab, whichever tab started it. */
  const closeLocalSession = useCallback(() => {
    signingOut.current = true;
    currentUser.current = null;
    setDraftOwner(null);
    saveAuthReturn(null);
    try {
      localStorage.removeItem(REMEMBER_KEY);
      sessionStorage.removeItem(REMEMBER_KEY);
    } catch {
      /* Storage is optional. */
    }
    setAccessToken(null);
    setUser(null);
    setSessionEnd('signed-out');
  }, []);

  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel(AUTH_CHANNEL);
    channel.onmessage = (event: MessageEvent<{ type?: string }>) => {
      if (event.data?.type !== 'signed-out' || !currentUser.current) return;
      closeLocalSession();
      signingOut.current = false;
    };
    return () => channel.close();
  }, [closeLocalSession]);

  const signOut = useCallback(async () => {
    closeLocalSession();
    if (typeof BroadcastChannel !== 'undefined') {
      const channel = new BroadcastChannel(AUTH_CHANNEL);
      channel.postMessage({ type: 'signed-out' });
      channel.close();
    }
    try {
      await authApi.logout();
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      // The local session is already closed; a network failure must not trap the UI.
    } finally {
      signingOut.current = false;
    }
  }, [closeLocalSession]);

  const updateUser = useCallback((profile: UserOut) => {
    currentUser.current = profile;
    setUser(profile);
  }, []);

  const value = useMemo(
    () => ({
      user,
      ready,
      sessionEnd,
      acknowledgeSessionEnd,
      signIn,
      acceptSession,
      completeGoogleSession,
      updateUser,
      signOut,
    }),
    [
      user,
      ready,
      sessionEnd,
      acknowledgeSessionEnd,
      signIn,
      acceptSession,
      completeGoogleSession,
      updateUser,
      signOut,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
