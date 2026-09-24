import { Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Outlet } from 'react-router-dom';
import { Brand } from '@/app/layout/Brand';
import { LocaleSwitcher, ThemeSwitcher } from '@/app/layout/HeaderControls';
import { SiteFooter } from '@/app/layout/SiteFooter';
import { Spinner } from '@/shared/ui/Spinner';
import { useAuth } from './useAuth';
import styles from './AuthLayout.module.css';

export function AuthLayout() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const home = user ? '/collection' : '/';
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Brand to={home} />
        <div className={styles.controls}>
          <LocaleSwitcher />
          <ThemeSwitcher />
        </div>
      </header>
      <main className={styles.card}>
        <Link to={home} className={styles.back}>
          {t('auth.backToSite')}
        </Link>
        <Suspense fallback={<Spinner />}>
          <Outlet />
        </Suspense>
      </main>
      <SiteFooter />
    </div>
  );
}
