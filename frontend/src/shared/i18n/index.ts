import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './en.json';
import uk from './uk.json';

const STORAGE_KEY = 'ck-locale';

export type Locale = 'uk' | 'en';

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'uk' || saved === 'en') return saved;
  } catch {
    /* default below */
  }
  return 'uk';
}

void i18n.use(initReactI18next).init({
  resources: {
    uk: { translation: uk },
    en: { translation: en },
  },
  lng: initialLocale(),
  fallbackLng: 'uk',
  interpolation: { escapeValue: false },
});

export function setLocale(locale: Locale): void {
  void i18n.changeLanguage(locale);
  document.documentElement.lang = locale;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* remembering is a convenience */
  }
}

export default i18n;
