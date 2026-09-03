import { useContext } from 'react';

import { ThemeContext } from './themeContext';
import type { ThemeContextValue } from './themeContext';

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used inside ThemeProvider');
  return context;
}
