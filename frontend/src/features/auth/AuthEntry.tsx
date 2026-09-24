import { useEffect, useRef, useState } from 'react';
import { Spinner } from '@/shared/ui';
import { GOOGLE_POPUP_CHANNEL, GOOGLE_POPUP_FLOW_KEY } from './googlePopup';
import { Navigate, useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from './useAuth';
import { guestDestination, readAuthReturn, safeAuthReturn } from './authReturn';
import type { AuthDialogMode } from './authDialogContext';

/** Compatibility URLs keep email links, bookmarks and OAuth callbacks working. */
export function AuthEntry({ mode }: { mode: AuthDialogMode }) {
  const { user } = useAuth();
  const location = useLocation();
  const [params] = useSearchParams();
  const state = location.state as { from?: string; email?: string } | null;
  const from = safeAuthReturn(state?.from) ?? readAuthReturn() ?? '/collection';
  const [flowId] = useState(() => {
    try {
      return sessionStorage.getItem(GOOGLE_POPUP_FLOW_KEY);
    } catch {
      return null;
    }
  });
  if (flowId && params.has('google') && typeof BroadcastChannel !== 'undefined') {
    return <GooglePopupResult flowId={flowId} mode={mode} google={params.get('google')!} />;
  }
  if (user && (mode === 'login' || mode === 'register')) return <Navigate to={from} replace />;
  return (
    <Navigate
      to={guestDestination(from)}
      replace
      state={{
        authRequest: { mode, from, email: state?.email, google: params.get('google') ?? undefined },
      }}
    />
  );
}

/** Return OAuth errors and verification instructions to the original tab too. */
function GooglePopupResult({
  flowId,
  mode,
  google,
}: {
  flowId: string;
  mode: AuthDialogMode;
  google: string;
}) {
  const sent = useRef(false);
  useEffect(() => {
    if (!sent.current) {
      sent.current = true;
      sessionStorage.removeItem(GOOGLE_POPUP_FLOW_KEY);
      const channel = new BroadcastChannel(GOOGLE_POPUP_CHANNEL);
      channel.postMessage({ type: 'result', flowId, mode, google });
      channel.close();
    }
    const timer = window.setTimeout(() => window.close(), 150);
    return () => window.clearTimeout(timer);
  }, [flowId, mode, google]);
  return <Spinner />;
}
