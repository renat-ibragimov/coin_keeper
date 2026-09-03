import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { Button, Input } from '@/shared/ui';

import * as authApi from '../api';
import { PasswordInput } from './PasswordInput';
import styles from './authForms.module.css';

export function RegisterPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
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
        password,
        displayName: displayName || undefined,
        website: website || undefined,
      });
      navigate('/check-email', { state: { email } });
    } catch (cause) {
      if (cause instanceof ApiError && cause.problemType === 'weak-password') {
        setError(t('auth.weakPassword'));
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
      <h2 className={styles.title}>{t('auth.registerTitle')}</h2>
      <p className={styles.subtitle}>{t('auth.registerSubtitle')}</p>
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
        <Input
          label={t('auth.displayName')}
          autoComplete="name"
          hint={t('auth.displayNameHint')}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />
        <PasswordInput
          label={t('auth.password')}
          autoComplete="new-password"
          required
          minLength={10}
          hint={t('auth.passwordHint')}
          placeholder={t('auth.passwordPlaceholder')}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
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
      <div className={styles.divider}>{t('common.or')}</div>
      <p className={styles.switch}>
        {t('auth.haveAccount')} <Link to="/login">{t('auth.signIn')}</Link>
      </p>
    </div>
  );
}
