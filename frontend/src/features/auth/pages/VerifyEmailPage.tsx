import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { Button, Spinner } from '@/shared/ui';

import { useAuth } from '../useAuth';
import * as authApi from '../api';
import styles from './authForms.module.css';

type VerifyState = 'pending' | 'success' | 'error' | 'missing-token';

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const { acceptSession } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<VerifyState>('pending');
  const started = useRef(false);

  const token = params.get('token');

  useEffect(() => {
    // React StrictMode mounts twice; the token is single-use, so guard.
    if (started.current) return;
    started.current = true;

    if (!token) {
      setState('missing-token');
      return;
    }
    (async () => {
      try {
        const session = await authApi.verifyEmail(token);
        acceptSession(session);
        setState('success');
      } catch {
        setState('error');
      }
    })();
  }, [token, acceptSession]);

  return (
    <div className={styles.centered}>
      <h2 className={styles.title}>{t('auth.verifyTitle')}</h2>
      {state === 'pending' ? (
        <>
          <Spinner />
          <p className={styles.subtitle}>{t('auth.verifyInProgress')}</p>
        </>
      ) : null}
      {state === 'success' ? (
        <>
          <div className={styles.formInfo}>{t('auth.verifySuccess')}</div>
          <Button onClick={() => navigate('/catalog', { replace: true })}>
            {t('auth.goToApp')}
          </Button>
        </>
      ) : null}
      {state === 'error' ? (
        <>
          <div className={styles.formError}>{t('auth.verifyError')}</div>
          <p className={styles.switch}>
            <Link to="/login">{t('auth.goToLogin')}</Link>
          </p>
        </>
      ) : null}
      {state === 'missing-token' ? (
        <div className={styles.formError}>{t('auth.verifyMissingToken')}</div>
      ) : null}
    </div>
  );
}
