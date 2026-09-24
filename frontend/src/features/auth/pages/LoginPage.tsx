import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button, Input } from '@/shared/ui';

import { useAuth } from '../useAuth';
import { saveAuthReturn, takeAuthReturn } from '../authReturn';
import { PasswordInput } from './PasswordInput';
import { GoogleSignIn } from './GoogleSignIn';
import type { AuthDialogMode } from '../authDialogContext';
import styles from './authForms.module.css';

export function LoginForm({
  from,
  onSuccess,
  onSwitch,
  onGoogleResult,
  onForgot,
  google,
  showHeading = true,
}: {
  from: string;
  onSuccess: () => void;
  onSwitch?: () => void;
  onGoogleResult?: (mode: AuthDialogMode, google: string) => void;
  onForgot?: () => void;
  google?: string;
  showHeading?: boolean;
}) {
  const { t } = useTranslation();
  const { signIn } = useAuth();
  const [params] = useSearchParams();
  const googleResult = google ?? params.get('google');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signIn(email, password, remember);
      takeAuthReturn();
      onSuccess();
    } catch (cause) {
      if (cause instanceof ApiError && cause.problemType === 'invalid-credentials') {
        setError(t('auth.invalidCredentials'));
      } else if (cause instanceof ApiError && cause.problemType === 'email-not-verified') {
        setError(t('auth.emailNotVerified'));
      } else if (cause instanceof ApiError && cause.status === 429) {
        setError(t('errors.rateLimited'));
      } else {
        setError(t('errors.generic'));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {showHeading ? <h2 className={styles.title}>{t('auth.loginTitle')}</h2> : null}
      <p className={styles.subtitle}>{t('auth.loginSubtitle')}</p>
      <form className={styles.form} onSubmit={(event) => void submit(event)}>
        {googleResult === 'link-required' ? (
          <div className={styles.formInfo}>{t('auth.googleLinkRequired')}</div>
        ) : googleResult ? (
          <div className={styles.formError}>{t('auth.googleError')}</div>
        ) : null}
        {error ? <div className={styles.formError}>{error}</div> : null}
        <Input
          label={t('auth.email')}
          type="email"
          autoFocus={!showHeading}
          autoComplete="email"
          required
          placeholder={t('auth.emailPlaceholder')}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <PasswordInput
          label={t('auth.password')}
          autoComplete="current-password"
          required
          placeholder={t('auth.passwordPlaceholder')}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <div className={styles.row}>
          <label className={styles.checkbox}>
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            {t('auth.rememberMe')}
          </label>
          {onForgot ? (
            <button type="button" className={styles.textButton} onClick={onForgot}>
              {t('auth.forgotPassword')}
            </button>
          ) : (
            <Link to="/forgot-password" onClick={() => saveAuthReturn(from)}>
              {t('auth.forgotPassword')}
            </Link>
          )}
        </div>
        <Button type="submit" block loading={busy}>
          {t('auth.signIn')}
        </Button>
      </form>
      <GoogleSignIn onResult={onGoogleResult} returnTo={from} onSuccess={onSuccess} />
      <div className={styles.divider}>{t('common.or')}</div>
      <p className={styles.switch}>
        {t('auth.noAccount')}{' '}
        {onSwitch ? (
          <button type="button" className={styles.textButton} onClick={onSwitch}>
            {t('auth.createAccount')}
          </button>
        ) : (
          <Link to="/register" state={{ from }}>
            {t('auth.createAccount')}
          </Link>
        )}
      </p>
    </div>
  );
}
