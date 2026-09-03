import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';
import en from '@/shared/i18n/en.json';
import uk from '@/shared/i18n/uk.json';
import { ThemeContext } from '@/shared/theme/themeContext';
import type { Theme } from '@/shared/theme/themeContext';

import { Brand } from './Brand';

// jsdom has no matchMedia, so the theme is provided directly instead of via ThemeProvider.
function renderWithTheme(ui: ReactElement, theme: Theme = 'light') {
  return render(
    <ThemeContext.Provider value={{ theme, toggleTheme: () => {} }}>
      <MemoryRouter>{ui}</MemoryRouter>
    </ThemeContext.Provider>,
  );
}

describe('Brand', () => {
  it('renders the full logo with the brand name as alt text, linking to the overview', () => {
    renderWithTheme(<Brand />);
    expect(screen.getByRole('img', { name: 'Bakost Numismatics' })).toHaveAttribute(
      'src',
      '/brand/logo-full-800.png',
    );
    expect(screen.getByRole('link', { name: 'Bakost Numismatics' })).toHaveAttribute('href', '/');
  });

  it('switches to the dark-theme wordmark file on the dark theme', () => {
    renderWithTheme(<Brand />, 'dark');
    expect(screen.getByRole('img', { name: 'Bakost Numismatics' })).toHaveAttribute(
      'src',
      '/brand/logo-full-dark-800.png',
    );
  });

  it('keeps the old product name out of the interface strings', () => {
    for (const bundle of [uk, en]) {
      expect(JSON.stringify(bundle)).not.toMatch(/coinkeeper/i);
    }
  });
});

// jsdom swaps the global URL class, so the file path is built from the module URL string.
const PUBLIC_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../public');

describe('web app manifest', () => {
  const manifest = JSON.parse(
    readFileSync(path.join(PUBLIC_DIR, 'manifest.webmanifest'), 'utf8'),
  ) as Record<string, unknown>;

  it('carries the brand and the generated icons', () => {
    expect(manifest.name).toBe('Bakost Numismatics');
    expect(manifest.short_name).toBe('Numismatics');
    expect(manifest.start_url).toBe('/');
    expect(manifest.display).toBe('standalone');
    expect(manifest.theme_color).toMatch(/^#[0-9a-f]{6}$/);
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/);
    const icons = manifest.icons as { src: string; sizes: string; purpose?: string }[];
    expect(icons.map((icon) => icon.sizes)).toEqual(['192x192', '512x512', '512x512']);
    expect(icons.some((icon) => icon.purpose === 'maskable')).toBe(true);
  });

  it('points at files that exist in public/', () => {
    const icons = manifest.icons as { src: string }[];
    for (const icon of icons) {
      expect(() => readFileSync(path.join(PUBLIC_DIR, icon.src))).not.toThrow();
    }
  });
});
