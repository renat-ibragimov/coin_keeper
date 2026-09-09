import { Monitor, Moon, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { setLocale } from '@/shared/i18n';
import type { Locale } from '@/shared/i18n';
import { useTheme } from '@/shared/theme/useTheme';
import type { ThemePreference } from '@/shared/theme/themeContext';

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

const THEME_OPTIONS: { value: ThemePreference; icon: typeof Sun; labelKey: string }[] = [
  { value: 'light', icon: Sun, labelKey: 'settings.themeLight' },
  { value: 'dark', icon: Moon, labelKey: 'settings.themeDark' },
  { value: 'system', icon: Monitor, labelKey: 'settings.themeSystem' },
];

export function ThemeSwitcher() {
  const { preference, setPreference } = useTheme();
  const { t } = useTranslation();
  return (
    <span className={styles.locales}>
      {THEME_OPTIONS.map(({ value, icon: Icon, labelKey }) => (
        <button
          key={value}
          type="button"
          className={[styles.locale, preference === value ? styles.localeActive : ''].join(' ')}
          onClick={() => setPreference(value)}
          aria-pressed={preference === value}
          aria-label={t(labelKey)}
          title={t(labelKey)}
        >
          <Icon size={15} aria-hidden="true" />
        </button>
      ))}
    </span>
  );
}
