import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { ThemeContext } from './themeContext';
import type { Theme, ThemePreference } from './themeContext';

const STORAGE_KEY = 'ck-theme';

function readPreference(): ThemePreference {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved;
  } catch {
    /* storage unavailable: fall through to the system preference */
  }
  return 'system';
}

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function resolve(preference: ThemePreference): Theme {
  return preference === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : preference;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [theme, setTheme] = useState<Theme>(() => resolve(preference));

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Live: a visitor on 'system' who switches their OS theme sees it without
  // touching the app — the same live tracking a 'light'/'dark' pick opts out of.
  useEffect(() => {
    if (preference !== 'system') return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setTheme(resolve('system'));
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
    setTheme(resolve(next));
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* remembering is a convenience, not a requirement */
    }
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, preference, setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}
