import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button, Spinner } from '@/shared/ui';

import { useAuth } from '../useAuth';
import * as authApi from '../api';
import { takeAuthReturn } from '../authReturn';
import { PasswordInput } from './PasswordInput';
import styles from './authForms.module.css';

type VerifyState = 'form' | 'pending' | 'success' | 'error' | 'missing-token';

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const token = params.get('token');
  const google = params.get('google') === '1';
  const { acceptSession } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<VerifyState>(
    token ? (google ? 'pending' : 'form') : 'missing-token',
  );
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    window.history.replaceState(window.history.state, '', window.location.pathname);
    if (!google || !token || started.current) return;
    started.current = true;
    void authApi.verifyEmail(token).then(
      (session) => {
        acceptSession(session);
        setState('success');
      },
      () => setState('error'),
    );
  }, [token, google, acceptSession]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (password !== repeat) {
      setMessage(t('auth.passwordsDontMatch'));
      return;
    }
    setMessage(null);
    setState('pending');
    try {
      const session = await authApi.verifyEmail(token, password);
      acceptSession(session);
      setState('success');
    } catch (cause) {
      setState('form');
      if (cause instanceof ApiError && cause.problemType === 'weak-password') {
        setMessage(t('auth.weakPassword'));
      } else if (cause instanceof ApiError && cause.problemType === 'invalid-verification-token') {
        setState('error');
      } else {
        setMessage(t('errors.generic'));
      }
    }
  }

  return (
    <div className={styles.centered}>
      <h2 className={styles.title}>{t('auth.verifyTitle')}</h2>
      {state === 'form' ? (
        <form className={styles.form} onSubmit={(event) => void submit(event)}>
          <p className={styles.subtitle}>{t('auth.verifySetPassword')}</p>
          {message ? <div className={styles.formError}>{message}</div> : null}
          <PasswordInput
            label={t('auth.newPassword')}
            autoComplete="new-password"
            required
            minLength={10}
            hint={t('auth.passwordHint')}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <PasswordInput
            label={t('auth.repeatPassword')}
            autoComplete="new-password"
            required
            value={repeat}
            onChange={(event) => setRepeat(event.target.value)}
          />
          <Button type="submit" block>
            {t('auth.verifySubmit')}
          </Button>
        </form>
      ) : null}
      {state === 'pending' ? (
        <>
          <Spinner />
          <p className={styles.subtitle}>{t('auth.verifyInProgress')}</p>
        </>
      ) : null}
      {state === 'success' ? (
        <>
          <div className={styles.formInfo}>{t('auth.verifySuccess')}</div>
          <Button
            onClick={() => {
              navigate(takeAuthReturn() ?? '/', {
                replace: true,
              });
            }}
          >
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
