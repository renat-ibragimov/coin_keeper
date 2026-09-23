import { lazy, Suspense, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';

import { Button, Modal, Spinner } from '@/shared/ui';

import * as authApi from './api';
import { safeAuthReturn } from './authReturn';
import { AuthDialogContext } from './authDialogContext';
import type { AuthDialogMode, AuthDialogPurpose } from './authDialogContext';
import styles from './pages/authForms.module.css';

const LoginForm = lazy(() =>
  import('./pages/LoginPage').then((module) => ({ default: module.LoginForm })),
);
const RegisterForm = lazy(() =>
  import('./pages/RegisterPage').then((module) => ({ default: module.RegisterForm })),
);

type DialogState = {
  mode: AuthDialogMode | 'check-email';
  from: string;
  purpose?: AuthDialogPurpose;
  email?: string;
};

export function AuthDialogProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const [cooldown, setCooldown] = useState(60);
  const [sentAgain, setSentAgain] = useState(false);

  useEffect(() => {
    if (dialog?.mode !== 'check-email' || cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((current) => current - 1), 1000);
    return () => clearTimeout(timer);
  }, [dialog?.mode, cooldown]);

  function open(
    mode: AuthDialogMode = 'login',
    options?: { from?: string; purpose?: AuthDialogPurpose },
  ) {
    setDialog({
      mode,
      from: safeAuthReturn(options?.from) ?? location.pathname + location.search,
      purpose: options?.purpose,
    });
  }

  async function resend() {
    if (!dialog?.email) return;
    setCooldown(60);
    setSentAgain(false);
    try {
      await authApi.resendVerification(dialog.email);
      setSentAgain(true);
    } catch {
      setSentAgain(false);
    }
  }

  const title =
    dialog?.mode === 'check-email'
      ? t('auth.checkEmailTitle')
      : dialog?.mode === 'register' && dialog.purpose === 'collection'
        ? t('guest.addTitle')
        : t(dialog?.mode === 'register' ? 'auth.registerTitle' : 'auth.loginTitle');

  return (
    <AuthDialogContext.Provider value={open}>
      {children}
      <Modal
        open={dialog !== null}
        onClose={() => setDialog(null)}
        title={title}
        size="sm"
        mobilePlacement="center"
      >
        <Suspense fallback={<Spinner />}>
          {dialog?.mode === 'login' ? (
            <LoginForm
              from={dialog.from}
              showHeading={false}
              onSuccess={() => setDialog(null)}
              onSwitch={() => setDialog({ ...dialog, mode: 'register' })}
            />
          ) : dialog?.mode === 'register' ? (
            <>
              {dialog.purpose === 'collection' ? (
                <p className={styles.subtitle}>{t('guest.addText')}</p>
              ) : null}
              <RegisterForm
                from={dialog.from}
                showHeading={false}
                onSuccess={(email) => {
                  setCooldown(60);
                  setSentAgain(false);
                  setDialog({ ...dialog, mode: 'check-email', email });
                }}
                onGoogleSuccess={() => setDialog(null)}
                onSwitch={() => setDialog({ ...dialog, mode: 'login' })}
              />
            </>
          ) : dialog?.mode === 'check-email' ? (
            <div className={styles.centered}>
              <p className={styles.subtitle}>{t('auth.checkEmailText', { email: dialog.email })}</p>
              {sentAgain ? <div className={styles.formInfo}>{t('auth.resendDone')}</div> : null}
              <Button variant="secondary" disabled={cooldown > 0} onClick={() => void resend()}>
                {cooldown > 0 ? t('auth.resendCountdown', { seconds: cooldown }) : t('auth.resend')}
              </Button>
              <button
                type="button"
                className={styles.textButton}
                onClick={() => setDialog({ ...dialog, mode: 'login' })}
              >
                {t('auth.goToLogin')}
              </button>
            </div>
          ) : null}
        </Suspense>
      </Modal>
    </AuthDialogContext.Provider>
  );
}
