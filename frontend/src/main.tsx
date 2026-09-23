// Self-hosted fonts. Each weight file carries every subset with
// unicode-range, Ukrainian glyphs included (checked for U+0490 ґ).
import '@fontsource/playfair-display/400.css';
import '@fontsource/playfair-display/600.css';
import '@fontsource/playfair-display/700.css';
import '@fontsource/source-sans-3/400.css';
import '@fontsource/source-sans-3/600.css';
import '@fontsource/source-sans-3/700.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@/shared/i18n';
import '@/shared/theme/tokens.css';

import { App } from './app/App';

// The browser's own scroll restoration races with App.tsx's ScrollToTop and
// is what made the coin card page land mid-scroll or at the bottom instead
// of the top; App.tsx owns scroll position on every navigation instead.
if ('scrollRestoration' in window.history) {
  window.history.scrollRestoration = 'manual';
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
