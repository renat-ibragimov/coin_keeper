import { useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';

import type { AuthDialogMode } from '../authDialogContext';
import * as authApi from '../api';
import { saveAuthReturn, takeAuthReturn } from '../authReturn';
import { useAuth } from '../useAuth';
import { GOOGLE_POPUP_CHANNEL, GOOGLE_POPUP_FLOW_KEY } from '../googlePopup';
import styles from './authForms.module.css';

const GOOGLE_START = '/api/v1/auth/google/start';

export function GoogleSignIn({
  returnTo,
  onSuccess,
  onResult,
}: {
  returnTo?: string;
  onSuccess?: () => void;
  onResult?: (mode: AuthDialogMode, google: string) => void;
}) {
  const { t } = useTranslation();
  const { completeGoogleSession } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState(false);
  const cleanup = useRef<(() => void) | null>(null);

  useEffect(() => {
    void authApi
      .googleStatus()
      .then((status) => setEnabled(status.enabled))
      .catch(() => {});
  }, []);

  useEffect(() => () => cleanup.current?.(), []);

  function start(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    event.preventDefault();
    saveAuthReturn(returnTo);
    setError(false);

    if (typeof BroadcastChannel === 'undefined') {
      window.location.replace(GOOGLE_START);
      return;
    }
    const popup = window.open('', '_blank', 'popup,width=500,height=700');
    if (!popup) {
      window.location.replace(GOOGLE_START);
      return;
    }

    const flowId = crypto.randomUUID();
    const channel = new BroadcastChannel(GOOGLE_POPUP_CHANNEL);
    let completed = false;
    const stop = () => {
      channel.close();
      clearInterval(closedCheck);
      cleanup.current = null;
    };
    cleanup.current?.();
    cleanup.current = stop;

    const finish = () => {
      if (completed) return;
      completed = true;
      stop();
      popup.close();
      void completeGoogleSession(true)
        .then(() => {
          takeAuthReturn();
          onSuccess?.();
        })
        .catch(() => setError(true));
    };
    channel.onmessage = (
      message: MessageEvent<{
        type?: string;
        flowId?: string;
        mode?: AuthDialogMode;
        google?: string;
      }>,
    ) => {
      if (message.data?.flowId !== flowId) return;
      if (message.data.type === 'complete') finish();
      if (message.data.type === 'result' && !completed) {
        completed = true;
        stop();
        popup.close();
        if (onResult)
          onResult(
            message.data.mode === 'check-email' ? 'check-email' : 'login',
            message.data.google ?? 'error',
          );
        else setError(true);
      }
    };
    const closedCheck = setInterval(() => {
      if (popup.closed) stop();
    }, 500);

    // This is still same-origin about:blank. The marker stays with the popup
    // through Google and lets the callback signal this exact flow back here.
    try {
      popup.sessionStorage.setItem(GOOGLE_POPUP_FLOW_KEY, flowId);
      popup.opener = null;
      popup.location.replace(new URL(GOOGLE_START, window.location.origin).href);
    } catch {
      stop();
      popup.close();
      window.location.replace(GOOGLE_START);
    }
  }

  if (!enabled) return null;
  return (
    <p className={styles.switch}>
      <a href={GOOGLE_START} onClick={start}>
        {t('auth.continueWithGoogle')}
      </a>
      {error ? <span className={styles.formError}>{t('auth.googleError')}</span> : null}
    </p>
  );
}
