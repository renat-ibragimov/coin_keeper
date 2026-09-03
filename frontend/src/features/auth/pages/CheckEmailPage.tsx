import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { Button } from '@/shared/ui';

import * as authApi from '../api';
import styles from './authForms.module.css';

const RESEND_COOLDOWN_SECONDS = 60;

export function CheckEmailPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const email = (location.state as { email?: string } | null)?.email ?? '';

  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS);
  const [sentAgain, setSentAgain] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => setCooldown((value) => value - 1), 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  async function resend() {
    if (!email) return;
    setSentAgain(false);
    setCooldown(RESEND_COOLDOWN_SECONDS);
    try {
      await authApi.resendVerification(email);
      setSentAgain(true);
    } catch {
      // The endpoint always answers 202; only network failures land here.
      setSentAgain(false);
    }
  }

  return (
    <div className={styles.centered}>
      <h2 className={styles.title}>{t('auth.checkEmailTitle')}</h2>
      <p className={styles.subtitle}>{t('auth.checkEmailText', { email })}</p>
      {sentAgain ? <div className={styles.formInfo}>{t('auth.resendDone')}</div> : null}
      <Button variant="secondary" disabled={cooldown > 0 || !email} onClick={() => void resend()}>
        {cooldown > 0 ? t('auth.resendCountdown', { seconds: cooldown }) : t('auth.resend')}
      </Button>
      <p className={styles.switch}>
        <Link to="/login">{t('auth.goToLogin')}</Link>
      </p>
    </div>
  );
}
