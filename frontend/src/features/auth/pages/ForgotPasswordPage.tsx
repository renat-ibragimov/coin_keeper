import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button, Input } from '@/shared/ui';

import * as authApi from '../api';
import styles from './authForms.module.css';

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await authApi.forgotPassword(email);
      setSent(true);
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 429
          ? t('errors.rateLimited')
          : t('errors.generic'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 className={styles.title}>{t('auth.forgotTitle')}</h2>
      <p className={styles.subtitle}>{t('auth.forgotText')}</p>
      {sent ? (
        <div className={styles.centered}>
          <div className={styles.formInfo}>{t('auth.forgotSent')}</div>
          <p className={styles.switch}>
            <Link to="/login">{t('auth.goToLogin')}</Link>
          </p>
        </div>
      ) : (
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
          <Button type="submit" block loading={busy}>
            {t('auth.sendResetLink')}
          </Button>
          <p className={styles.switch}>
            <Link to="/login">{t('auth.goToLogin')}</Link>
          </p>
        </form>
      )}
    </div>
  );
}
