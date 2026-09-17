import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import * as authApi from '../api';
import { saveAuthReturn } from '../authReturn';
import styles from './authForms.module.css';

export function GoogleSignIn({ returnTo }: { returnTo?: string }) {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    void authApi
      .googleStatus()
      .then((status) => setEnabled(status.enabled))
      .catch(() => {});
  }, []);

  if (!enabled) return null;
  return (
    <p className={styles.switch}>
      <a href="/api/v1/auth/google/start" onClick={() => saveAuthReturn(returnTo)}>
        {t('auth.continueWithGoogle')}
      </a>
    </p>
  );
}
