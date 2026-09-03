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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
