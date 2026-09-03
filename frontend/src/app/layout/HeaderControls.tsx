import { useTranslation } from 'react-i18next';

import { setLocale } from '@/shared/i18n';
import type { Locale } from '@/shared/i18n';
import { useTheme } from '@/shared/theme/useTheme';

import styles from './HeaderControls.module.css';

export function LocaleSwitcher() {
  const { i18n } = useTranslation();
  const current = (i18n.language === 'en' ? 'en' : 'uk') as Locale;
  const option = (locale: Locale, label: string) => (
    <button
      type="button"
      className={[styles.locale, current === locale ? styles.localeActive : ''].join(' ')}
      onClick={() => setLocale(locale)}
      aria-pressed={current === locale}
    >
      {label}
    </button>
  );
  return (
    <span className={styles.locales}>
      {option('uk', 'UA')}
      <span className={styles.divider}>/</span>
      {option('en', 'EN')}
    </span>
  );
}

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useTranslation();
  return (
    <button
      type="button"
      className={styles.themeToggle}
      onClick={toggleTheme}
      aria-label={t('header.themeToggle')}
      title={t('header.themeToggle')}
    >
      {theme === 'light' ? '☾' : '☀'}
    </button>
  );
}
