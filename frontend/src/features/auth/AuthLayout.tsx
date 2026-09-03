import { useTranslation } from 'react-i18next';
import { Outlet } from 'react-router-dom';

import { Brand } from '@/app/layout/Brand';
import { LocaleSwitcher, ThemeToggle } from '@/app/layout/HeaderControls';

import styles from './AuthLayout.module.css';

const FEATURES = [
  { icon: '❦', title: 'auth.featureCatalogTitle', text: 'auth.featureCatalogText' },
  { icon: '◈', title: 'auth.featureCollectionTitle', text: 'auth.featureCollectionText' },
  { icon: '↗', title: 'auth.featurePricesTitle', text: 'auth.featurePricesText' },
] as const;

export function AuthLayout() {
  const { t } = useTranslation();
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Brand variant="full" to="/login" />
        <div className={styles.controls}>
          <LocaleSwitcher />
          <ThemeToggle />
        </div>
      </header>
      <div className={styles.card}>
        <aside className={styles.welcome}>
          <h1 className={styles.welcomeTitle}>{t('auth.welcomeTitle')}</h1>
          <div className={styles.flourish} aria-hidden="true">
            ❧
          </div>
          <p className={styles.welcomeText}>{t('auth.welcomeText')}</p>
          <ul className={styles.features}>
            {FEATURES.map((feature) => (
              <li key={feature.title} className={styles.feature}>
                <span className={styles.featureIcon} aria-hidden="true">
                  {feature.icon}
                </span>
                <span>
                  <span className={styles.featureTitle}>{t(feature.title)}</span>
                  <span className={styles.featureText}>{t(feature.text)}</span>
                </span>
              </li>
            ))}
          </ul>
        </aside>
        <section className={styles.form}>
          <Outlet />
        </section>
      </div>
    </div>
  );
}
