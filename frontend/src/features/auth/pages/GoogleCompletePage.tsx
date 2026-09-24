import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { Spinner } from '@/shared/ui';

import { useAuth } from '../useAuth';
import { takeAuthReturn } from '../authReturn';
import { GOOGLE_POPUP_CHANNEL, GOOGLE_POPUP_FLOW_KEY } from '../googlePopup';
import styles from './authForms.module.css';

export function GoogleCompletePage() {
  const { t } = useTranslation();
  const { completeGoogleSession } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const isLink = params.get('mode') === 'link';
  const linkResult = params.get('google');
  const started = useRef(false);
  const [popupFlowId] = useState(() => sessionStorage.getItem(GOOGLE_POPUP_FLOW_KEY));
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!isLink && popupFlowId) {
      sessionStorage.removeItem(GOOGLE_POPUP_FLOW_KEY);
      if (typeof BroadcastChannel !== 'undefined') {
        const channel = new BroadcastChannel(GOOGLE_POPUP_CHANNEL);
        channel.postMessage({ type: 'complete', flowId: popupFlowId });
        channel.close();
        const closeTimer = window.setTimeout(() => window.close(), 150);
        return () => window.clearTimeout(closeTimer);
      }
    }
    if (started.current) return;
    started.current = true;
    void completeGoogleSession(isLink ? undefined : true)
      .then(() => {
        navigate(
          isLink
            ? `/settings?google=${linkResult ?? 'error'}`
            : (takeAuthReturn() ?? '/collection'),
          {
            replace: true,
          },
        );
      })
      .catch(() => setError(true));
  }, [completeGoogleSession, navigate, isLink, linkResult, popupFlowId]);

  return (
    <div className={styles.centered}>
      {error ? (
        <>
          <p className={styles.formError}>{t('auth.googleError')}</p>
          <Link to="/login">{t('auth.goToLogin')}</Link>
        </>
      ) : (
        <Spinner />
      )}
    </div>
  );
}
