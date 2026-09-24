import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button, Input } from '@/shared/ui';

import * as authApi from '../api';
import { saveAuthReturn } from '../authReturn';
import { GoogleSignIn } from './GoogleSignIn';
import type { AuthDialogMode } from '../authDialogContext';
import styles from './authForms.module.css';

export function RegisterForm({
  from,
  onSuccess,
  onSwitch,
  onGoogleResult,
  onGoogleSuccess,
  showHeading = true,
}: {
  from?: string;
  onSuccess: (email: string) => void;
  onSwitch?: () => void;
  onGoogleResult?: (mode: AuthDialogMode, google: string) => void;
  onGoogleSuccess?: () => void;
  showHeading?: boolean;
}) {
  const { t } = useTranslation();

  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [website, setWebsite] = useState(''); // honeypot, docs/07-auth.md
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await authApi.register({
        email,
        displayName: displayName || undefined,
        website: website || undefined,
      });
      saveAuthReturn(from);
      onSuccess(email);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 429) {
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
      {showHeading ? <h2 className={styles.title}>{t('auth.registerTitle')}</h2> : null}
      <p className={styles.subtitle}>{t('auth.registerSubtitle')}</p>
      <form className={styles.form} onSubmit={(event) => void submit(event)}>
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
        <Input
          label={t('auth.displayName')}
          autoComplete="name"
          hint={t('auth.displayNameHint')}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />
        <div className={styles.honeypot} aria-hidden="true">
          <input
            type="text"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
          />
        </div>
        <Button type="submit" block loading={busy}>
          {t('auth.signUp')}
        </Button>
      </form>
      <GoogleSignIn onResult={onGoogleResult} returnTo={from ?? '/'} onSuccess={onGoogleSuccess} />
      <div className={styles.divider}>{t('common.or')}</div>
      <p className={styles.switch}>
        {t('auth.haveAccount')}{' '}
        {onSwitch ? (
          <button type="button" className={styles.textButton} onClick={onSwitch}>
            {t('auth.signIn')}
          </button>
        ) : (
          <Link to="/login" state={{ from }}>
            {t('auth.signIn')}
          </Link>
        )}
      </p>
    </div>
  );
}
