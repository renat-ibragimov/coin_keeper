import { createContext } from 'react';

/** What is actually painted — data-theme on <html> is always one of these. */
export type Theme = 'light' | 'dark';

/** What the visitor chose. 'system' tracks the OS setting live. */
export type ThemePreference = Theme | 'system';

export interface ThemeContextValue {
  theme: Theme;
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);
