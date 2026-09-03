import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button } from '@/shared/ui';

import * as authApi from '../api';
import { PasswordInput } from './PasswordInput';
import styles from './authForms.module.css';

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get('token');

  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (password !== repeat) {
      setError(t('auth.passwordsDontMatch'));
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
    } catch (cause) {
      if (cause instanceof ApiError && cause.problemType === 'weak-password') {
        setError(t('auth.weakPassword'));
      } else if (cause instanceof ApiError && cause.problemType === 'invalid-reset-token') {
        setError(t('auth.resetError'));
      } else if (cause instanceof ApiError && cause.status === 429) {
        setError(t('errors.rateLimited'));
      } else {
        setError(t('errors.generic'));
      }
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div className={styles.centered}>
        <h2 className={styles.title}>{t('auth.resetTitle')}</h2>
        <div className={styles.formError}>{t('auth.resetError')}</div>
        <p className={styles.switch}>
          <Link to="/forgot-password">{t('auth.forgotTitle')}</Link>
        </p>
      </div>
    );
  }

  if (done) {
    return (
      <div className={styles.centered}>
        <h2 className={styles.title}>{t('auth.resetTitle')}</h2>
        <div className={styles.formInfo}>{t('auth.resetSuccess')}</div>
        <p className={styles.switch}>
          <Link to="/login">{t('auth.goToLogin')}</Link>
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className={styles.title}>{t('auth.resetTitle')}</h2>
      <p className={styles.subtitle}>{t('auth.resetText')}</p>
      <form className={styles.form} onSubmit={(event) => void submit(event)}>
        {error ? <div className={styles.formError}>{error}</div> : null}
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
        <Button type="submit" block loading={busy}>
          {t('auth.resetSubmit')}
        </Button>
      </form>
    </div>
  );
}
