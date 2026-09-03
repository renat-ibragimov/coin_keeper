import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button, Input } from '@/shared/ui';

import { useAuth } from '../useAuth';
import { PasswordInput } from './PasswordInput';
import styles from './authForms.module.css';

export function LoginPage() {
  const { t } = useTranslation();
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signIn(email, password, remember);
      navigate(from, { replace: true });
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
      <h2 className={styles.title}>{t('auth.loginTitle')}</h2>
      <p className={styles.subtitle}>{t('auth.loginSubtitle')}</p>
      <form className={styles.form} onSubmit={(event) => void submit(event)}>
        {error ? <div className={styles.formError}>{error}</div> : null}
        <Input
          label={t('auth.email')}
          type="email"
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
          <Link to="/forgot-password">{t('auth.forgotPassword')}</Link>
        </div>
        <Button type="submit" block loading={busy}>
          {t('auth.signIn')}
        </Button>
      </form>
      <div className={styles.divider}>{t('common.or')}</div>
      <p className={styles.switch}>
        {t('auth.noAccount')} <Link to="/register">{t('auth.createAccount')}</Link>
      </p>
    </div>
  );
}
