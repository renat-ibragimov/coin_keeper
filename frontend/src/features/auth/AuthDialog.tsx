import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { Button, Modal, Spinner } from '@/shared/ui';
import * as authApi from './api';
import { guestDestination, safeAuthReturn, saveAuthReturn } from './authReturn';
import { AuthDialogContext } from './authDialogContext';
import type { AuthDialogMode, AuthDialogOptions } from './authDialogContext';
import { useAuth } from './useAuth';
import styles from './pages/authForms.module.css';

const LoginForm = lazy(() => import('./pages/LoginPage').then((m) => ({ default: m.LoginForm })));
const RegisterForm = lazy(() =>
  import('./pages/RegisterPage').then((m) => ({ default: m.RegisterForm })),
);
const ForgotPasswordForm = lazy(() =>
  import('./pages/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordForm })),
);
type DialogState = AuthDialogOptions & { mode: AuthDialogMode; from: string; keepReturn?: boolean };

export function AuthDialogProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { sessionEnd, acknowledgeSessionEnd } = useAuth();
  const [dialog, setDialog] = useState<DialogState | null>(null);
  const currentDialog = useRef(dialog);
  currentDialog.current = dialog;
  const [cooldown, setCooldown] = useState(60);
  const [sentAgain, setSentAgain] = useState(false);
  const path = location.pathname + location.search + location.hash;

  const open = useCallback(
    (mode: AuthDialogMode = 'login', options?: AuthDialogOptions) => {
      setCooldown(60);
      setSentAgain(false);
      setDialog({
        ...options,
        mode,
        from: safeAuthReturn(options?.from) ?? safeAuthReturn(path) ?? '/collection',
      });
    },
    [path],
  );

  // Close on ordinary navigation, but consume auth redirects on their public background.
  useEffect(() => {
    setDialog(null);
  }, [path]);
  useEffect(() => {
    const state = location.state as { authRequest?: DialogState } | null;
    if (!state?.authRequest) return;
    const { authRequest, ...rest } = state;
    open(authRequest.mode, authRequest);
    navigate(path, { replace: true, state: rest });
  }, [location.state, navigate, open, path]);

  useEffect(() => {
    if (!sessionEnd) return;
    const state = location.state as {
      sessionEndHandled?: string;
      authRequest?: DialogState;
    } | null;
    if (state?.sessionEndHandled === sessionEnd) {
      acknowledgeSessionEnd();
      if (!state.authRequest) navigate(path, { replace: true, state: null });
      return;
    }
    setDialog(null);
    navigate(guestDestination(path), {
      replace: true,
      state: {
        sessionEndHandled: sessionEnd,
        ...(sessionEnd === 'expired'
          ? {
              authRequest: {
                mode: 'login',
                reason: 'expired',
                from: path,
                returnState: location.state,
              },
            }
          : {}),
      },
    });
  }, [sessionEnd, acknowledgeSessionEnd, navigate, path, location.state]);

  useEffect(() => {
    if (dialog?.mode !== 'check-email' || cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [dialog?.mode, cooldown]);

  function close() {
    if (dialog?.mode !== 'check-email' && !dialog?.keepReturn) saveAuthReturn(null);
    setDialog(null);
  }
  function complete() {
    if (!dialog || currentDialog.current !== dialog) return;
    const destination = dialog.from;
    setDialog(null);
    if (destination !== path) navigate(destination, { replace: true, state: dialog.returnState });
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
      : dialog?.mode === 'forgot-password'
        ? t('auth.forgotTitle')
        : dialog?.mode === 'register' && dialog.purpose === 'collection'
          ? t('guest.addTitle')
          : t(dialog?.mode === 'register' ? 'auth.registerTitle' : 'auth.loginTitle');

  return (
    <AuthDialogContext.Provider value={open}>
      {children}
      <Modal
        open={dialog !== null}
        onClose={close}
        title={title}
        size="sm"
        mobilePlacement="center"
        dismissOnNavigation={false}
      >
        {dialog?.reason === 'expired' ? (
          <p role="status" className={styles.formInfo}>
            {t('auth.sessionExpired')}
          </p>
        ) : null}
        <Suspense fallback={<Spinner />}>
          {dialog?.mode === 'login' ? (
            <LoginForm
              from={dialog.from}
              showHeading={false}
              google={dialog.google}
              onGoogleResult={(mode, google) => setDialog({ ...dialog, mode, google })}
              onSuccess={complete}
              onForgot={() => setDialog({ ...dialog, mode: 'forgot-password', google: undefined })}
              onSwitch={() => setDialog({ ...dialog, mode: 'register', google: undefined })}
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
                  if (currentDialog.current !== dialog) return;
                  setCooldown(60);
                  setSentAgain(false);
                  setDialog({ ...dialog, mode: 'check-email', email });
                }}
                onGoogleSuccess={complete}
                onGoogleResult={(mode, google) => setDialog({ ...dialog, mode, google })}
                onSwitch={() => setDialog({ ...dialog, mode: 'login' })}
              />
            </>
          ) : dialog?.mode === 'forgot-password' ? (
            <ForgotPasswordForm
              from={dialog.from}
              onSent={() => {
                if (currentDialog.current === dialog) setDialog({ ...dialog, keepReturn: true });
              }}
              onBack={() => setDialog({ ...dialog, mode: 'login' })}
            />
          ) : dialog?.mode === 'check-email' ? (
            <div className={styles.centered}>
              <p className={styles.subtitle}>
                {dialog.google === 'verify'
                  ? t('auth.googleCheckEmail')
                  : dialog.email
                    ? t('auth.checkEmailText', { email: dialog.email })
                    : t('auth.checkEmailGeneric')}
              </p>
              {sentAgain ? <div className={styles.formInfo}>{t('auth.resendDone')}</div> : null}
              {dialog.email ? (
                <Button variant="secondary" disabled={cooldown > 0} onClick={() => void resend()}>
                  {cooldown > 0
                    ? t('auth.resendCountdown', { seconds: cooldown })
                    : t('auth.resend')}
                </Button>
              ) : null}
              <button
                type="button"
                className={styles.textButton}
                onClick={() => setDialog({ ...dialog, mode: 'login', google: undefined })}
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
