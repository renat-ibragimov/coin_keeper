import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { Spinner } from '@/shared/ui';

import { useAuth } from '../useAuth';
import styles from './authForms.module.css';

export function GoogleCompletePage() {
  const { t } = useTranslation();
  const { completeGoogleSession } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const isLink = params.get('mode') === 'link';
  const linkResult = params.get('google');
  const started = useRef(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void completeGoogleSession(isLink ? undefined : true)
      .then(() => {
        navigate(isLink ? `/settings?google=${linkResult ?? 'error'}` : '/collection', {
          replace: true,
        });
      })
      .catch(() => setError(true));
  }, [completeGoogleSession, navigate, isLink, linkResult]);

  return (
    <div className={styles.centered}>
      {error ? (
        <>
          <p className={styles.formError}>{t('auth.googleError')}</p>
          <Link to="/login">{t('auth.goToLogin')}</Link>
        </>
      ) : (
        <Spinner />
      )}
    </div>
  );
}
